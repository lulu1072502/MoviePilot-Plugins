"""在插件页面集中展示识别结果并标记 R18（成人内容）。

数据来自宿主稳定的只读查询 SDK（``app.sdk.queries``）：

- 整理历史 ``list_transfer_history`` —— 整理流程的识别结果
- 下载历史 ``list_download_history`` —— 下载流程的识别结果
- 订阅 ``list_subscriptions`` —— 订阅的识别结果

这些快照只带媒体身份（``media_source`` + ``media_id``），不含成人标记，因此
插件按身份补判定：当来源为 ``themoviedb`` 且开关打开时，用宿主内置的 TMDB 客户端
读取该 ID 的详情并取 ``adult`` 字段；判定结果按 TTL 缓存复用，避免重复请求。
其它来源（豆瓣、Bangumi、IMDb 等）没有等价字段，统一显示为「未判定」，不会伪造标记。

页面为 Vuetify JSON 模式（``get_render_mode()`` 默认 vuetify），由 MoviePilot
前端的内置 ``PageRender`` 渲染：每行一个卡片，成人条目显示红色 R18 徽标。
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from threading import RLock
from typing import Any, Dict, List, Optional, Tuple

from app.plugins import _PluginBase
from app.sdk.logging import logger
from app.sdk.queries import (
    MAX_QUERY_PAGE_SIZE,
    QueryPageRequest,
    list_download_history,
    list_subscriptions,
    list_transfer_history,
)

# 宿主内置数据来源编号（等价于 MediaSource.TMDB = "themoviedb"）
_TMDB_SOURCE = "themoviedb"
# R18 判定结果缓存有效期（秒）
_ADULT_TTL_SECONDS = 7 * 24 * 3600
# 判定缓存条目上限，超限时丢弃最早写入的部分
_ADULT_CACHE_LIMIT = 2000
# 判定缓存存放键
_CACHE_KEY = "adult_cache"
# 每类来源最多显示的条数
_MAX_COUNT = min(50, int(MAX_QUERY_PAGE_SIZE))

# 来源分组
_SOURCE_ALL = "全部"
_SOURCE_TRANSFER = "整理历史"
_SOURCE_DOWNLOAD = "下载历史"
_SOURCE_SUBSCRIBE = "订阅"
_SOURCE_OPTIONS: Tuple[str, ...] = (_SOURCE_ALL, _SOURCE_TRANSFER, _SOURCE_DOWNLOAD, _SOURCE_SUBSCRIBE)
_GROUPED_SOURCES: Tuple[str, ...] = (_SOURCE_TRANSFER, _SOURCE_DOWNLOAD, _SOURCE_SUBSCRIBE)

# 进程内复用的宿主 TMDB 客户端（与宿主 tmdb 模块同样长生命周期持有）
_TMDB_LOCK = RLock()
_TMDB_CLIENT: Optional[Any] = None


@dataclass(frozen=True)
class _Row:
    """一行识别结果及其 R18 判定。"""

    source: str
    title: str
    year: str
    mtype: str
    date: str
    media_source: Optional[str]
    media_id: Optional[str]
    adult: Optional[bool]


def _clamp_int(value: Any, default: int, low: int, high: int) -> int:
    """把配置值安全地夹到 [low, high] 范围。"""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _text(value: Any) -> str:
    """把可能为空的值规范为字符串。"""
    if value is None:
        return ""
    return str(value).strip()


def _tmdb_client() -> Optional[Any]:
    """惰性获取宿主 TMDB 客户端；宿主结构变化时返回 None 而不是抛异常。"""
    global _TMDB_CLIENT
    with _TMDB_LOCK:
        if _TMDB_CLIENT is not None:
            return _TMDB_CLIENT
        try:
            from app.modules.themoviedb.tmdbapi import TmdbApi
        except Exception as err:  # pragma: no cover - 取决于宿主结构
            logger.error(f"R18标志：导入宿主 TMDB 客户端失败：{err}")
            return None
        try:
            _TMDB_CLIENT = TmdbApi()
        except Exception as err:
            logger.error(f"R18标志：初始化宿主 TMDB 客户端失败：{err}")
            return None
        return _TMDB_CLIENT


def _fetch_tmdb_adult(media_id: str) -> Optional[bool]:
    """按 TMDB ID 读取详情里的 adult 字段；查询失败返回 None。"""
    client = _tmdb_client()
    if client is None:
        return None
    try:
        tmdbid = int(media_id)
    except (TypeError, ValueError):
        return None
    try:
        info = client.get_info(mtype=None, tmdbid=tmdbid)
    except Exception as err:  # 网络失败、限流、无效 ID 等都不应影响整页展示
        logger.warning(f"R18标志：查询 TMDB {tmdbid} 详情失败：{err}")
        return None
    if not isinstance(info, dict):
        return None
    return bool(info.get("adult"))


class R18Marker(_PluginBase):
    """识别结果 R18 标志插件。"""

    plugin_name = "R18标志"
    plugin_desc = "在插件页面集中展示识别结果（整理历史/下载历史/订阅），为成人内容条目显示 R18 标志。"
    plugin_icon = "Moviepilot_A.png"
    plugin_version = "1.0.0"
    plugin_author = "Ken"
    author_url = "https://github.com/lulu1072502"
    plugin_config_prefix = "r18marker_"
    plugin_order = 50
    auth_level = 1

    _enabled = False
    _source = _SOURCE_ALL
    _count = 10
    _adult_text = "R18"
    _resolve_tmdb = True

    def init_plugin(self, config: dict | None = None) -> None:
        """读取配置；按宿主约定允许重复调用。"""
        config = config or {}
        self._enabled = bool(config.get("enabled"))
        source = _text(config.get("source")) or _SOURCE_ALL
        self._source = source if source in _SOURCE_OPTIONS else _SOURCE_ALL
        self._count = _clamp_int(config.get("count"), default=10, low=1, high=_MAX_COUNT)
        self._adult_text = _text(config.get("adult_text")) or "R18"
        self._resolve_tmdb = bool(config.get("resolve_tmdb", True))
        logger.info(
            "R18标志：配置生效，enabled=%s，来源=%s，每类条数=%s，TMDB判定=%s",
            self._enabled,
            self._source,
            self._count,
            self._resolve_tmdb,
        )

    def get_state(self) -> bool:
        """返回插件是否启用。"""
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """本插件不注册远程命令。"""
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        """注册只读结果接口与判定缓存刷新接口。"""
        return [
            {
                "path": "/results",
                "endpoint": self.api_results,
                "methods": ["GET"],
                "summary": "R18 识别结果",
                "description": "返回当前来源配置下的识别结果清单及其 R18 判定。",
            },
            {
                "path": "/refresh",
                "endpoint": self.api_refresh,
                "methods": ["GET"],
                "summary": "清空 R18 判定缓存",
                "description": "清空成人内容判定缓存，下次展示时重新向数据来源查询。",
            },
        ]

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """返回配置页面与默认配置，插件默认开启。"""
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VAlert",
                                        "props": {
                                            "type": "info",
                                            "variant": "tonal",
                                            "text": (
                                                "本插件把整理历史、下载历史、订阅中的识别结果集中到一个页面，"
                                                "对成人内容条目显示 R18 标志。判定方式：媒体身份为 TMDB 时读取该 ID 的 "
                                                "adult 字段；其它来源无等价字段，显示为「未判定」。"
                                            ),
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 3},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {"model": "enabled", "label": "启用插件"},
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 3},
                                "content": [
                                    {
                                        "component": "VSelect",
                                        "props": {
                                            "model": "source",
                                            "label": "数据来源",
                                            "items": list(_SOURCE_OPTIONS),
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 2},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "count",
                                            "label": "每类条数",
                                            "placeholder": f"1 - {_MAX_COUNT}",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 2},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "adult_text",
                                            "label": "标志文字",
                                            "placeholder": "R18",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 2},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "resolve_tmdb",
                                            "label": "调用 TMDB 判定",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                ],
            }
        ], {
            "enabled": True,
            "source": _SOURCE_ALL,
            "count": 10,
            "adult_text": "R18",
            "resolve_tmdb": True,
        }

    def get_page(self) -> List[dict]:
        """返回详情页：识别结果清单 + R18 标志。"""
        if not self._enabled:
            return [_alert("warning", "插件未启用：请在插件配置中开启后查看识别结果。")]

        rows = self._collect_rows()
        if not rows:
            return [
                _alert("info", "暂无识别结果：整理历史、下载历史或订阅中还没有匹配的记录。"),
                self._refresh_button(),
            ]

        r18_rows = [row for row in rows if row.adult is True]
        unknown_rows = [row for row in rows if row.adult is None]
        page: List[dict] = [
            _alert(
                "info",
                f"识别结果共 {len(rows)} 条，其中 R18 {len(r18_rows)} 条，"
                f"未判定 {len(unknown_rows)} 条。来源范围：{self._source}；每类最多 {self._count} 条。",
            )
        ]
        if not self._resolve_tmdb:
            page.append(_alert("warning", "已关闭 TMDB 判定：除宿主自带标记外，其余条目都显示为「未判定」。"))
        page.extend(self._render_row(row) for row in rows)
        page.append(self._refresh_button())
        return page

    def stop_service(self) -> None:
        """停用插件时释放运行状态；进程内 TMDB 客户端由宿主进程自行管理。"""
        self._enabled = False

    # ---------------------------------------------------------------- API

    def api_results(self) -> Any:
        """返回识别结果清单（含 R18 判定），供页面事件或其它调用方使用。"""
        rows = self._collect_rows()
        return {
            "success": True,
            "message": "R18标志：识别结果",
            "source": self._source,
            "count": self._count,
            "total": len(rows),
            "r18": sum(1 for row in rows if row.adult is True),
            "unknown": sum(1 for row in rows if row.adult is None),
            "items": [asdict(row) for row in rows],
        }

    def api_refresh(self) -> Any:
        """清空 R18 判定缓存。"""
        self.save_data(_CACHE_KEY, {})
        logger.info("R18标志：判定缓存已清空")
        return {"success": True, "message": "R18 判定缓存已清空"}

    # ------------------------------------------------------------- 数据读取

    def _active_sources(self) -> Tuple[str, ...]:
        """返回本次需要读取的来源分组。"""
        if self._source == _SOURCE_ALL:
            return _GROUPED_SOURCES
        if self._source in _GROUPED_SOURCES:
            return (self._source,)
        return ()

    def _collect_rows(self) -> List[_Row]:
        """读取所有目标来源的识别结果。"""
        rows: List[_Row] = []
        for source in self._active_sources():
            try:
                rows.extend(self._query_source(source))
            except Exception as err:  # 单个来源失败不影响其它来源
                logger.error(f"R18标志：读取{source}失败：{err}")
        return rows

    def _query_source(self, source: str) -> List[_Row]:
        """按来源读取一页识别结果。"""
        page = QueryPageRequest(page=1, count=self._count)
        if source == _SOURCE_TRANSFER:
            return [self._row_from_snapshot(source, item) for item in list_transfer_history(page=page).items]
        if source == _SOURCE_DOWNLOAD:
            return [self._row_from_snapshot(source, item) for item in list_download_history(page=page).items]
        if source == _SOURCE_SUBSCRIBE:
            return [self._row_from_snapshot(source, item) for item in list_subscriptions(page=page).items]
        return []

    def _row_from_snapshot(self, source: str, snapshot: Any) -> _Row:
        """把只读快照转换为展示行，并补上 R18 判定。"""
        title = _text(getattr(snapshot, "name", None)) or _text(getattr(snapshot, "title", None))
        media_source = _text(getattr(snapshot, "media_source", None)) or None
        media_id = _text(getattr(snapshot, "media_id", None)) or None
        return _Row(
            source=source,
            title=title or "（无标题）",
            year=_text(getattr(snapshot, "year", None)),
            mtype=_text(getattr(snapshot, "type", None)),
            date=_text(getattr(snapshot, "date", None)),
            media_source=media_source,
            media_id=media_id,
            adult=self._adult_of(snapshot, media_source, media_id),
        )

    def _adult_of(self, snapshot: Any, media_source: Optional[str], media_id: Optional[str]) -> Optional[bool]:
        """优先用宿主提供的标记，其次按媒体身份解析。"""
        own = getattr(snapshot, "adult", None)
        if isinstance(own, bool):
            return own
        return self._resolve_adult(media_source, media_id)

    def _resolve_adult(self, media_source: Optional[str], media_id: Optional[str]) -> Optional[bool]:
        """按媒体身份解析成人标记，带 TTL 缓存。"""
        if not media_source or not media_id:
            return None
        cache_key = f"{media_source}:{media_id}"
        cache = self._adult_cache()
        cached = cache.get(cache_key)
        if isinstance(cached, dict):
            try:
                fresh = time.time() - float(cached.get("ts") or 0) < _ADULT_TTL_SECONDS
            except (TypeError, ValueError):
                fresh = False
            if fresh and isinstance(cached.get("adult"), bool):
                return bool(cached["adult"])

        if not self._resolve_tmdb or media_source != _TMDB_SOURCE:
            return None

        adult = _fetch_tmdb_adult(media_id)
        if adult is not None:
            self._store_adult(cache_key, adult)
        return adult

    def _adult_cache(self) -> Dict[str, Any]:
        """读取判定缓存，异常或脏数据时回退为空缓存。"""
        cache = self.get_data(_CACHE_KEY)
        return cache if isinstance(cache, dict) else {}

    def _store_adult(self, cache_key: str, adult: bool) -> None:
        """写入判定缓存并按上限裁剪。"""
        cache = self._adult_cache()
        cache[cache_key] = {"adult": bool(adult), "ts": time.time()}
        if len(cache) > _ADULT_CACHE_LIMIT:
            ordered = sorted(
                cache.items(),
                key=lambda item: float(item[1].get("ts") or 0) if isinstance(item[1], dict) else 0.0,
            )
            cache = dict(ordered[-_ADULT_CACHE_LIMIT:])
        try:
            self.save_data(_CACHE_KEY, cache)
        except Exception as err:
            logger.warning(f"R18标志：写入判定缓存失败：{err}")

    # ------------------------------------------------------------- 页面渲染

    def _render_row(self, row: _Row) -> dict:
        """渲染一行识别结果，成人条目显示 R18 徽标。"""
        parts = [f"{row.title}（{row.year}）" if row.year else row.title]
        if row.mtype:
            parts.append(row.mtype)
        parts.append(row.source)
        if row.media_source and row.media_id:
            parts.append(f"{row.media_source}:{row.media_id}")
        if row.date:
            parts.append(row.date)

        if row.adult is True:
            badge = _chip("error", "flat", self._adult_text)
        elif row.adult is None:
            badge = _chip("warning", "tonal", f"{self._adult_text} 未判定")
        else:
            badge = _chip("success", "tonal", "非 R18")

        return {
            "component": "VCard",
            "props": {"variant": "tonal", "class": "mb-2"},
            "content": [
                {
                    "component": "VCardText",
                    "content": [
                        {
                            "component": "VRow",
                            "props": {"align": "center"},
                            "content": [
                                {
                                    "component": "VCol",
                                    "props": {"cols": 12, "md": 9},
                                    "content": [
                                        {
                                            "component": "VCardText",
                                            "props": {"class": "pa-0 text-body-2"},
                                            "text": " · ".join(parts),
                                        }
                                    ],
                                },
                                {
                                    "component": "VCol",
                                    "props": {"cols": 12, "md": 3, "class": "d-flex justify-end"},
                                    "content": [badge],
                                },
                            ],
                        }
                    ],
                }
            ],
        }

    def _refresh_button(self) -> dict:
        """返回「重新判定」按钮：调用插件 API 并触发页面重新加载。"""
        return {
            "component": "VBtn",
            "props": {"color": "primary", "variant": "tonal", "class": "mt-2"},
            "text": "清空判定缓存并重新判定",
            "events": {
                "@click": {
                    "api": f"plugin/{self.__class__.__name__}/refresh",
                    "method": "GET",
                    "params": {},
                }
            },
        }


def _alert(alert_type: str, text: str) -> dict:
    """构造 VAlert 页面节点。"""
    return {"component": "VAlert", "props": {"type": alert_type, "variant": "tonal", "text": text}}


def _chip(color: str, variant: str, text: str) -> dict:
    """构造 VChip 徽标节点。"""
    return {"component": "VChip", "props": {"color": color, "variant": variant, "size": "small"}, "text": text}
