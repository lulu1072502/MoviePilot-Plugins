"""R18Marker 插件自检：用桩模块验证页面、关键词判定与识别词写入逻辑。

覆盖：
1. 页面统计正确（总数 / R18 / 未判定）；
2. 三种徽标：R18（红）、R18 未判定（黄）、非 R18（绿）；
3. 非 TMDB 来源不做判定（未判定）且不调用 TMDB；
4. 关键词判定：命中 hentai(198385) 时 r18_source == "keyword"，关键词接口不可用时回退 adult；
5. 判定结果带缓存，重复渲染不重复查询；刷新接口清空缓存后可重新判定；
6. 识别词：status 统计、apply 合并写入、重复 apply 幂等、保留用户已有规则、extra_identifiers 生效；
7. 插件未启用时页面给出提示。

运行：python tests/v3/r18marker/test_plugin.py
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_FILE = REPO_ROOT / "plugins.v3" / "r18marker" / "__init__.py"

TMDB_ADULT_CALLS: list[str] = []
TMDB_KEYWORD_CALLS: list[str] = []

# 宿主配置桩：模拟 SystemConfigKey.CustomIdentifiers 的读写
FAKE_CONFIG_VALUES: dict[str, object] = {}


class _Snapshot:
    """只读快照桩。"""

    def __init__(self, **kwargs: object) -> None:
        self.__dict__.update(kwargs)


class _Page:
    """分页结果桩。"""

    def __init__(self, items: list[object]) -> None:
        self.items = items
        self.total = len(items)


class _FakeConfigService:
    """模拟 app.application.configuration 的 SystemConfigService。"""

    def get(self, key: object = None) -> object:
        return FAKE_CONFIG_VALUES.get(str(key))

    def set(self, key: object, value: object) -> bool:
        FAKE_CONFIG_VALUES[str(key)] = value
        return True


def _install_stubs() -> None:
    """构造最小宿主桩：插件基类、日志、只读查询 SDK、系统配置。"""

    class _PluginBase:
        plugin_name = ""

        def __init__(self) -> None:
            self._store: dict[str, object] = {}

        def get_data(self, key=None, plugin_id=None):
            return self._store.get(key)

        def save_data(self, key, value, plugin_id=None) -> None:
            self._store[key] = value

        def del_data(self, key, plugin_id=None):
            return self._store.pop(key, None)

    class _Logger:
        def info(self, *args: object, **kwargs: object) -> None:
            pass

        def warning(self, *args: object, **kwargs: object) -> None:
            pass

        def error(self, *args: object, **kwargs: object) -> None:
            pass

        def debug(self, *args: object, **kwargs: object) -> None:
            pass

    class QueryPageRequest:
        def __init__(self, page: int = 1, count: int = 50, **kwargs: object) -> None:
            self.page = page
            self.count = count

    class SystemConfigKey:
        CustomIdentifiers = "CustomIdentifiers"

    transfer = [
        _Snapshot(
            title="某电影",
            year="2024",
            type="电影",
            date="2025-01-01 10:00:00",
            media_source="themoviedb",
            media_id="12345",
        )
    ]
    download = [
        _Snapshot(
            title="某下载",
            year="2023",
            type="电影",
            date="2025-01-02 10:00:00",
            media_source="douban",
            media_id="67890",
        )
    ]
    subscriptions = [
        _Snapshot(
            name="某剧集",
            year="2022",
            type="电视剧",
            date="2025-01-03 10:00:00",
            media_source="themoviedb",
            media_id="999",
        )
    ]

    def _module(name: str, **attrs: object) -> types.ModuleType:
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        sys.modules[name] = module
        return module

    app = _module("app")
    app.__path__ = []  # type: ignore[attr-defined]
    plugins = _module("app.plugins", _PluginBase=_PluginBase)
    plugins.__path__ = []  # type: ignore[attr-defined]
    sdk = _module("app.sdk")
    sdk.__path__ = []  # type: ignore[attr-defined]
    _module("app.sdk.logging", logger=_Logger())
    _module(
        "app.sdk.queries",
        MAX_QUERY_PAGE_SIZE=200,
        QueryPageRequest=QueryPageRequest,
        list_transfer_history=lambda filters=None, page=None: _Page(list(transfer)),
        list_download_history=lambda filters=None, page=None: _Page(list(download)),
        list_subscriptions=lambda filters=None, page=None: _Page(list(subscriptions)),
    )
    schemas = _module("app.schemas")
    schemas.__path__ = []  # type: ignore[attr-defined]
    _module("app.schemas.types", SystemConfigKey=SystemConfigKey)
    application = _module("app.application")
    application.__path__ = []  # type: ignore[attr-defined]
    _module(
        "app.application.configuration",
        get_configured_system_config=lambda: _FakeConfigService(),
    )


def _load_plugin():
    spec = importlib.util.spec_from_file_location("r18marker_plugin", PLUGIN_FILE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _walk(node: object):
    """深度遍历页面 JSON 节点。"""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def _chips(page: list[dict]) -> list[str]:
    """收集页面里的 VChip 文字。"""
    return [
        str(node.get("text"))
        for node in _walk(page)
        if isinstance(node, dict) and node.get("component") == "VChip"
    ]


def _alerts(page: list[dict]) -> list[str]:
    """收集页面里的 VAlert 文字。"""
    return [
        str(node.get("text"))
        for node in _walk(page)
        if isinstance(node, dict) and node.get("component") == "VAlert"
    ]


def main() -> None:
    _install_stubs()
    plugin_module = _load_plugin()

    def fake_adult(media_id: str):
        TMDB_ADULT_CALLS.append(media_id)
        return {"12345": True, "999": False}.get(media_id)

    plugin_module._fetch_tmdb_adult = fake_adult  # 隔离网络
    plugin_module._fetch_tmdb_keywords = lambda media_id, mtype="": None  # 默认走 adult 回退

    plugin = plugin_module.R18Marker()
    plugin.init_plugin({"enabled": True, "source": "全部", "count": 10, "adult_text": "R18", "resolve_tmdb": True})

    # 1. 统计
    page = plugin.get_page()
    alerts = _alerts(page)
    assert any("共 3 条" in t and "R18 1 条" in t and "未判定 1 条" in t for t in alerts), alerts

    # 2. 三种徽标
    chips = sorted(_chips(page))
    assert chips == sorted(["R18", "R18 未判定", "非 R18"]), chips

    # 3. 非 TMDB 来源未做判定
    assert "67890" not in TMDB_ADULT_CALLS, TMDB_ADULT_CALLS
    assert sorted(TMDB_ADULT_CALLS) == ["12345", "999"], TMDB_ADULT_CALLS

    # 4. 判定结果带缓存：再次渲染不重复查询
    calls_before = len(TMDB_ADULT_CALLS)
    plugin.get_page()
    assert len(TMDB_ADULT_CALLS) == calls_before, TMDB_ADULT_CALLS

    # 5. 刷新接口清空缓存后可重新判定
    assert plugin.api_refresh()["success"] is True
    plugin.get_page()
    assert len(TMDB_ADULT_CALLS) > calls_before, TMDB_ADULT_CALLS

    # 6. 关键词判定优先，且标注来源
    plugin_module._fetch_tmdb_keywords = lambda media_id, mtype="": [198385] if media_id == "12345" else []
    plugin.api_refresh()

    def fake_adult_should_not_be_used(media_id: str):
        TMDB_ADULT_CALLS.append(media_id)
        raise AssertionError("关键词可判定时不应回退 adult 字段")

    plugin_module._fetch_tmdb_adult = fake_adult_should_not_be_used
    result = plugin.api_results()
    items = {item["media_id"]: item for item in result["items"]}
    assert items["12345"]["adult"] is True and items["12345"]["r18_source"] == "keyword", items["12345"]
    assert items["999"]["adult"] is False and items["999"]["r18_source"] == "keyword", items["999"]

    # 关键词接口不可用时回退 adult
    plugin_module._fetch_tmdb_keywords = lambda media_id, mtype="": None
    plugin_module._fetch_tmdb_adult = fake_adult
    plugin.api_refresh()
    result = plugin.api_results()
    items = {item["media_id"]: item for item in result["items"]}
    assert items["12345"]["r18_source"] == "adult", items["12345"]

    # 7. 识别词：status / preview / apply
    status = plugin.api_identifiers_status()
    assert status["available"] is True, status
    assert status["builtin_count"] == 76 and status["host_count"] == 0, status
    assert status["missing"] == 76 and status["present"] == 0, status

    preview = plugin.api_identifiers_preview()
    assert preview["success"] is True and preview["total"] == 76 and preview["added"] == 76, preview
    # 预览不写入
    assert "CustomIdentifiers" not in FAKE_CONFIG_VALUES, FAKE_CONFIG_VALUES

    first = plugin.api_identifiers_apply()
    assert first["success"] is True and first["added"] == 76 and first["total"] == 76, first
    stored = FAKE_CONFIG_VALUES["CustomIdentifiers"]
    assert isinstance(stored, list) and len(stored) == 76, stored

    # 幂等：再写一次不再新增
    second = plugin.api_identifiers_apply()
    assert second["success"] is True and second["added"] == 0, second

    # 保留用户已有规则，只追加缺失项
    FAKE_CONFIG_VALUES["CustomIdentifiers"] = ["我的规则 => 替换", stored[0]]
    third = plugin.api_identifiers_apply()
    assert third["added"] == 75, third
    merged = FAKE_CONFIG_VALUES["CustomIdentifiers"]
    assert merged[0] == "我的规则 => 替换" and len(merged) == 77, merged[:3]

    # extra_identifiers 追加在内置规则之后
    plugin.init_plugin({"enabled": True, "extra_identifiers": "自定义追加规则 => 值"})
    assert plugin.api_identifiers_status()["builtin_count"] == 77
    FAKE_CONFIG_VALUES["CustomIdentifiers"] = []
    applied = plugin.api_identifiers_apply()
    assert applied["added"] == 77, applied
    assert FAKE_CONFIG_VALUES["CustomIdentifiers"][-1] == "自定义追加规则 => 值"

    # 8. 未启用时给出提示
    plugin.init_plugin({"enabled": False})
    page = plugin.get_page()
    assert any("插件未启用" in t for t in _alerts(page)), _alerts(page)
    assert plugin.get_state() is False

    # 9. 结果接口
    plugin.init_plugin({"enabled": True, "source": "整理历史", "count": 10, "resolve_tmdb": False})
    result = plugin.api_results()
    assert result["total"] == 1 and result["unknown"] == 1, result
    assert result["items"][0]["source"] == "整理历史", result["items"]

    print("OK：R18Marker 插件自检全部通过")


if __name__ == "__main__":
    main()
