"""IncludeAdult 插件自检：不依赖真实 MoviePilot 宿主，用桩模块验证补丁行为。

覆盖：
1. 开关开启时，未指定 adult 的搜索被注入 adult=True（含异步入口）；
2. 调用方显式指定 adult 时不覆盖；
3. 开关关闭时不注入；
4. 停用/重载后恢复原始方法；
5. 重复初始化不叠加包装层。

运行：python tests/v3/includeadult/test_plugin.py
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_FILE = REPO_ROOT / "plugins.v3" / "includeadult" / "__init__.py"

CALLS: list[tuple[str, str, object]] = []


def _install_stubs() -> None:
    """构造最小宿主桩：app.plugins._PluginBase、app.sdk.logging 与内置 TMDB 搜索类。"""

    class _PluginBase:
        plugin_name = ""

        def __init__(self) -> None:  # noqa: D107 - 桩实现
            pass

    class _Logger:
        def info(self, *args: object, **kwargs: object) -> None:
            pass

        def warning(self, *args: object, **kwargs: object) -> None:
            pass

        def error(self, *args: object, **kwargs: object) -> None:
            pass

    class Search:
        """按真实 tmdbv3api Search 的签名记录调用。"""

        def _record(self, api: str, term: str, adult: object) -> list[dict]:
            CALLS.append((api, term, adult))
            return [{"api": api, "term": term, "adult": adult}]

        def multi(self, term, adult=None, region=None, page=1):
            return self._record("multi", term, adult)

        def movies(self, term, adult=None, region=None, year=None, release_year=None, page=1):
            return self._record("movies", term, adult)

        def tv_shows(self, term, adult=None, release_year=None, page=1):
            return self._record("tv_shows", term, adult)

        def people(self, term, adult=None, region=None, page=1):
            return self._record("people", term, adult)

        async def async_multi(self, term, adult=None, region=None, page=1):
            return self._record("async_multi", term, adult)

        async def async_movies(self, term, adult=None, region=None, year=None, release_year=None, page=1):
            return self._record("async_movies", term, adult)

        async def async_tv_shows(self, term, adult=None, release_year=None, page=1):
            return self._record("async_tv_shows", term, adult)

        async def async_people(self, term, adult=None, region=None, page=1):
            return self._record("async_people", term, adult)

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
    modules = _module("app.modules")
    modules.__path__ = []  # type: ignore[attr-defined]
    themoviedb = _module("app.modules.themoviedb")
    themoviedb.__path__ = []  # type: ignore[attr-defined]
    tmdbv3api = _module("app.modules.themoviedb.tmdbv3api")
    tmdbv3api.__path__ = []  # type: ignore[attr-defined]
    objs = _module("app.modules.themoviedb.tmdbv3api.objs")
    objs.__path__ = []  # type: ignore[attr-defined]
    _module("app.modules.themoviedb.tmdbv3api.objs.search", Search=Search)


def _load_plugin():
    spec = importlib.util.spec_from_file_location("includeadult_plugin", PLUGIN_FILE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _last_call() -> tuple[str, str, object]:
    assert CALLS, "没有记录到任何搜索调用"
    return CALLS[-1]


def main() -> None:
    _install_stubs()
    plugin_module = _load_plugin()
    search_class = sys.modules["app.modules.themoviedb.tmdbv3api.objs.search"].Search

    # 1. 开关默认开启：未指定 adult 时注入 True
    plugin = plugin_module.IncludeAdult()
    plugin.init_plugin({"enabled": True, "include_adult": True})
    assert plugin.get_state() is True, "插件应报告运行中"

    client = search_class()
    for name in ("multi", "movies", "tv_shows", "people"):
        CALLS.clear()
        getattr(client, name)(term="测试")
        api, term, adult = _last_call()
        assert api == name and term == "测试", f"{name} 调用被改写：{_last_call()}"
        assert adult is True, f"{name} 未注入 adult=True：{adult}"

    for name in ("async_multi", "async_movies", "async_tv_shows", "async_people"):
        CALLS.clear()
        asyncio.run(getattr(client, name)(term="测试"))
        api, _term, adult = _last_call()
        assert api == name, f"{name} 调用被改写：{_last_call()}"
        assert adult is True, f"{name} 未注入 adult=True：{adult}"

    # 2. 显式指定 adult 时不覆盖
    for explicit in (False, True):
        CALLS.clear()
        client.movies(term="测试", adult=explicit)
        assert _last_call()[2] is explicit, f"显式 adult={explicit} 被覆盖：{_last_call()}"
    CALLS.clear()
    client.multi("测试", True)
    assert _last_call()[2] is True, f"位置参数 adult 被改写：{_last_call()}"

    # 3. 开关关闭时不注入
    plugin.init_plugin({"enabled": True, "include_adult": False})
    CALLS.clear()
    client.multi(term="测试")
    assert _last_call()[2] is None, f"开关关闭仍在注入：{_last_call()}"

    # 4. 重复初始化不叠加包装层
    plugin.init_plugin({"enabled": True, "include_adult": True})
    depth = len(list(_wrapper_chain(search_class.movies)))
    assert depth == 1, f"包装层叠加，实际层数={depth}"
    CALLS.clear()
    client.multi(term="测试")
    assert _last_call()[2] is True, "重复初始化后注入失效"

    # 5. 停用后恢复原始方法
    plugin.stop_service()
    assert plugin.get_state() is False, "停用后不应报告运行中"
    assert not getattr(search_class.movies, "_mp_include_adult_wrapper", False), "未恢复原始方法"
    CALLS.clear()
    client.multi(term="测试")
    assert _last_call()[2] is None, f"停用后仍在注入：{_last_call()}"

    print("OK：IncludeAdult 插件自检全部通过")


def _wrapper_chain(method):
    """遍历 functools.wraps 形成的包装链。"""
    while getattr(method, "_mp_include_adult_wrapper", False):
        yield method
        method = getattr(method, "__wrapped__", None)
        if method is None:
            return


if __name__ == "__main__":
    main()
