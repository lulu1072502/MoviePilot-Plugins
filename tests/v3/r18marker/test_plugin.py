"""R18Marker 插件自检：不依赖真实 MoviePilot 宿主，用桩模块验证页面与判定逻辑。

覆盖：
1. 页面顶部统计正确（总数 / R18 / 未判定）；
2. 三种徽标：R18（红）、R18 未判定（黄）、非 R18（绿）；
3. 非 TMDB 来源不做判定（未判定）且不调用 TMDB；
4. TMDB 判定结果带缓存，重复渲染不重复查询；
5. 刷新接口清空缓存后可重新判定；
6. 插件未启用时页面给出提示。

运行：python tests/v3/r18marker/test_plugin.py
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_FILE = REPO_ROOT / "plugins.v3" / "r18marker" / "__init__.py"

TMDB_CALLS: list[str] = []


class _Snapshot:
    """只读快照桩。"""

    def __init__(self, **kwargs: object) -> None:
        self.__dict__.update(kwargs)


class _Page:
    """分页结果桩。"""

    def __init__(self, items: list[object]) -> None:
        self.items = items
        self.total = len(items)


def _install_stubs() -> None:
    """构造最小宿主桩：插件基类、日志、只读查询 SDK。"""

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

    class QueryPageRequest:
        def __init__(self, page: int = 1, count: int = 50, **kwargs: object) -> None:
            self.page = page
            self.count = count

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
    _module("app.plugins", _PluginBase=_PluginBase).__path__ = []  # type: ignore[attr-defined]
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

    def fake_fetch(media_id: str):
        TMDB_CALLS.append(media_id)
        return {"12345": True, "999": False}.get(media_id)

    plugin_module._fetch_tmdb_adult = fake_fetch  # 隔离网络

    plugin = plugin_module.R18Marker()
    plugin.init_plugin({"enabled": True, "source": "全部", "count": 10, "adult_text": "R18", "resolve_tmdb": True})

    # 1. 统计
    page = plugin.get_page()
    alerts = _alerts(page)
    assert any("共 3 条" in text and "R18 1 条" in text and "未判定 1 条" in text for text in alerts), alerts

    # 2. 三种徽标
    chips = sorted(_chips(page))
    assert chips == sorted(["R18", "R18 未判定", "非 R18"]), chips

    # 3. 非 TMDB 来源未做判定
    assert "67890" not in TMDB_CALLS, TMDB_CALLS
    assert sorted(TMDB_CALLS) == ["12345", "999"], TMDB_CALLS

    # 4. 判定结果带缓存：再次渲染不重复查询
    calls_before = len(TMDB_CALLS)
    plugin.get_page()
    assert len(TMDB_CALLS) == calls_before, f"缓存未生效：{TMDB_CALLS}"

    # 5. 刷新接口清空缓存后可重新判定
    assert plugin.api_refresh()["success"] is True
    plugin.get_page()
    assert len(TMDB_CALLS) > calls_before, f"清空缓存后未重新判定：{TMDB_CALLS}"

    # 6. 未启用时给出提示
    plugin.init_plugin({"enabled": False})
    page = plugin.get_page()
    assert any("插件未启用" in text for text in _alerts(page)), _alerts(page)
    assert plugin.get_state() is False

    # 7. 结果接口
    plugin.init_plugin({"enabled": True, "source": "整理历史", "count": 10, "resolve_tmdb": False})
    result = plugin.api_results()
    assert result["total"] == 1 and result["unknown"] == 1, result
    assert result["items"][0]["source"] == "整理历史", result["items"]

    print("OK：R18Marker 插件自检全部通过")


if __name__ == "__main__":
    main()
