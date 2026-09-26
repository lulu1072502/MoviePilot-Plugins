"""让 MoviePilot 的 TMDB 识别与搜索默认包含成人内容（include_adult=true）。

宿主的识别/搜索统一走 ``app.modules.themoviedb.tmdbapi.TmdbApi``，它最终调用内置
``tmdbv3api`` 搜索客户端 ``Search`` 的以下方法：

- ``multi`` / ``async_multi``       —— ``TmdbApi.search_multiis``（``/search/multi``）
- ``movies`` / ``async_movies``     —— ``TmdbApi.search_movies``（``/search/movie``）
- ``tv_shows`` / ``async_tv_shows`` —— ``TmdbApi.search_tvs``（``/search/tv``）
- ``people`` / ``async_people``     —— ``TmdbApi.search_persons``（``/search/person``）

这些方法只在调用方显式传入 ``adult`` 时才会拼上 ``include_adult`` 参数，而宿主自身
从不传，因此 TMDB 始终按默认的 ``include_adult=false`` 过滤成人内容。本插件在这些
搜索方法外做一层包装：

1. 调用方未指定 ``adult`` 时补上 ``adult=True``（覆盖 ``search_multiis`` 多类型搜索）；
2. 调用方显式指定 ``adult``（True/False）时不覆盖，尊重调用意图；
3. 插件关闭或停用时恢复原始方法，不向请求注入任何参数。

补丁状态与原始方法都挂在目标类上，因此插件模块被宿主重新加载后行为仍然一致。
"""

from __future__ import annotations

from functools import wraps
from importlib import import_module
from threading import RLock
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.plugins import _PluginBase
from app.sdk.logging import logger

# 目标：内置 TMDB 搜索客户端
_TARGET_MODULE = "app.modules.themoviedb.tmdbv3api.objs.search"
_TARGET_CLASS = "Search"

# 需要包装的搜索方法（``async_`` 前缀表示异步入口）
_SEARCH_METHODS: Tuple[str, ...] = (
    "multi",
    "movies",
    "tv_shows",
    "people",
    "async_multi",
    "async_movies",
    "async_tv_shows",
    "async_people",
)

# 运行时状态与原始方法保存在目标类上，避免插件模块重载后状态分叉
_STATE_ATTR = "_mp_include_adult_state"
_ORIGINALS_ATTR = "_mp_include_adult_originals"
_WRAPPER_MARKER = "_mp_include_adult_wrapper"

_PATCH_LOCK = RLock()


def _resolve_search_class() -> Optional[type]:
    """解析内置 TMDB 搜索客户端类；宿主结构变化时返回 None 而不是抛异常。"""
    try:
        module = import_module(_TARGET_MODULE)
    except Exception as err:  # pragma: no cover - 取决于宿主结构
        logger.error(f"识别包含成人内容：导入 {_TARGET_MODULE} 失败：{err}")
        return None
    search_class = getattr(module, _TARGET_CLASS, None)
    if not isinstance(search_class, type):
        logger.error(f"识别包含成人内容：{_TARGET_MODULE} 中未找到 {_TARGET_CLASS}")
        return None
    return search_class


def _should_inject(owner: Any) -> bool:
    """读取目标类上的实时状态，判断本次调用是否补上 adult=True。"""
    state = getattr(type(owner), _STATE_ATTR, None)
    if not isinstance(state, dict):
        return False
    return bool(state.get("enabled") and state.get("include_adult"))


def _make_wrapper(original: Callable[..., Any], method_name: str) -> Callable[..., Any]:
    """包装一个搜索方法：仅在调用方未指定 adult 时补上 adult=True。"""

    def inject(target_self: Any, args: Tuple[Any, ...], kwargs: Dict[str, Any]) -> None:
        # args 已去掉 self：长度 >= 2 说明 adult 由位置参数显式传入，保持原样
        if len(args) < 2 and kwargs.get("adult") is None and _should_inject(target_self):
            kwargs["adult"] = True

    if method_name.startswith("async_"):

        @wraps(original)
        async def async_wrapper(client_self: Any, *args: Any, **kwargs: Any) -> Any:
            inject(client_self, args, kwargs)
            return await original(client_self, *args, **kwargs)

        wrapped: Callable[..., Any] = async_wrapper
    else:

        @wraps(original)
        def sync_wrapper(client_self: Any, *args: Any, **kwargs: Any) -> Any:
            inject(client_self, args, kwargs)
            return original(client_self, *args, **kwargs)

        wrapped = sync_wrapper

    setattr(wrapped, _WRAPPER_MARKER, True)
    return wrapped


def _install_patch(include_adult: bool) -> List[str]:
    """安装（或复用）搜索方法包装并刷新实时状态，返回本次新包装的方法名。"""
    search_class = _resolve_search_class()
    if search_class is None:
        return []
    wrapped_now: List[str] = []
    with _PATCH_LOCK:
        originals: Dict[str, Callable[..., Any]] = dict(
            getattr(search_class, _ORIGINALS_ATTR, None) or {}
        )
        for method_name in _SEARCH_METHODS:
            method = getattr(search_class, method_name, None)
            if not callable(method):
                continue
            if getattr(method, _WRAPPER_MARKER, False):
                # 已经由本插件（可能是上一次加载）包装过，只刷新状态即可
                continue
            originals[method_name] = method
            setattr(search_class, method_name, _make_wrapper(method, method_name))
            wrapped_now.append(method_name)
        setattr(search_class, _ORIGINALS_ATTR, originals)
        setattr(search_class, _STATE_ATTR, {"enabled": True, "include_adult": include_adult})
    return wrapped_now


def _remove_patch() -> List[str]:
    """恢复被包装的搜索方法并关闭注入，返回恢复的方法名。"""
    search_class = _resolve_search_class()
    if search_class is None:
        return []
    restored: List[str] = []
    with _PATCH_LOCK:
        originals: Dict[str, Callable[..., Any]] = getattr(search_class, _ORIGINALS_ATTR, None) or {}
        for method_name, original in originals.items():
            setattr(search_class, method_name, original)
            restored.append(method_name)
        setattr(search_class, _ORIGINALS_ATTR, {})
        setattr(search_class, _STATE_ATTR, {"enabled": False, "include_adult": False})
    return sorted(restored)


def _patched_methods() -> List[str]:
    """返回当前仍被本插件包装的方法名。"""
    search_class = _resolve_search_class()
    if search_class is None:
        return []
    return [
        method_name
        for method_name in _SEARCH_METHODS
        if getattr(getattr(search_class, method_name, None), _WRAPPER_MARKER, False)
    ]


class IncludeAdult(_PluginBase):
    """让 TMDB 识别与搜索默认携带 include_adult=true 的本地插件。"""

    plugin_name = "识别包含成人内容"
    plugin_desc = (
        "让 TMDB 识别与搜索默认携带 include_adult=true，"
        "覆盖多类型搜索 search_multiis 以及电影/剧集/人物搜索。"
    )
    plugin_icon = "Moviepilot_A.png"
    plugin_version = "1.0.0"
    plugin_author = "Ken"
    author_url = "https://github.com/lulu1072502"
    plugin_config_prefix = "includeadult_"
    plugin_order = 50
    auth_level = 1

    _enabled = False
    _include_adult = True
    _installed = False
    _patched: List[str] = []

    def init_plugin(self, config: dict | None = None) -> None:
        """读取配置并安装 TMDB 搜索补丁；按宿主约定允许重复调用。"""
        # 重复初始化时先还原，避免包装层叠加
        self.stop_service()
        config = config or {}
        self._enabled = bool(config.get("enabled"))
        self._include_adult = bool(config.get("include_adult", True))

        if not self._enabled:
            logger.info("识别包含成人内容：插件未启用，保持 TMDB 原始搜索行为")
            return

        wrapped_now = _install_patch(self._include_adult)
        self._patched = _patched_methods()
        self._installed = bool(self._patched)
        if not self._installed:
            logger.error("识别包含成人内容：未能包装内置 TMDB 搜索方法，插件未生效")
            return
        logger.info(
            "识别包含成人内容：已生效，include_adult=%s，本次新包装=%s，当前已包装=%s",
            self._include_adult,
            ",".join(wrapped_now) or "无（复用已有包装）",
            ",".join(self._patched),
        )

    def get_state(self) -> bool:
        """仅在补丁实际接管内置 TMDB 搜索时报告运行中。"""
        return bool(self._enabled and self._installed)

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """本插件不注册远程命令。"""
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        """本插件不注册后端 API。"""
        return []

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """返回配置页面与默认配置，开关默认开启。"""
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
                                                "开启后，TMDB 搜索会带上 include_adult=true，"
                                                "识别与搜索（含 search_multiis 多类型搜索）结果将包含成人内容。"
                                                "调用方显式指定 adult 的请求不受影响，关闭开关即恢复原行为。"
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
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "enabled",
                                            "label": "启用插件",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "include_adult",
                                            "label": "识别时包含成人内容（include_adult=true）",
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
            "include_adult": True,
        }

    def get_page(self) -> List[dict]:
        """返回详情页：展示补丁状态与已包装的搜索方法。"""
        patched = _patched_methods()
        state = "运行中" if self.get_state() else "未生效"
        lines = [
            f"插件状态：{state}",
            f"include_adult 开关：{'已开启' if self._include_adult else '已关闭'}",
            f"插件启用开关：{'已开启' if self._enabled else '已关闭'}",
            (
                "已包装的内置搜索方法：" + ",".join(patched)
                if patched
                else "已包装的内置搜索方法：无（插件未接管，TMDB 仍按 include_adult=false 过滤）"
            ),
            (
                "生效范围：search_multiis/async_search_multiis（多类型搜索）、"
                "search_movies/search_tvs（电影、剧集）及各自异步入口、search_persons（人物）。"
            ),
        ]
        alerts = [
            {
                "component": "VAlert",
                "props": {
                    "type": "success" if self.get_state() else "warning",
                    "variant": "tonal",
                    "text": lines[0],
                },
            }
        ]
        alerts.extend(
            {
                "component": "VAlert",
                "props": {"type": "info", "variant": "tonal", "text": line},
            }
            for line in lines[1:]
        )
        return alerts

    def stop_service(self) -> None:
        """停用或重载时恢复内置 TMDB 搜索方法，避免补丁残留。"""
        restored = _remove_patch()
        if restored:
            logger.info("识别包含成人内容：已恢复内置 TMDB 搜索方法：%s", ",".join(restored))
        self._installed = False
        self._patched = []
