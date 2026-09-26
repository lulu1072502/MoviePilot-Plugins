# 识别包含成人内容（IncludeAdult）

让 MoviePilot 的 TMDB 识别与搜索默认携带 `include_adult=true`。

## 它做了什么

宿主的识别/搜索统一由 `app.modules.themoviedb.tmdbapi.TmdbApi` 发起，最终落到内置
`tmdbv3api` 搜索客户端 `Search` 的这些方法：

| 内置搜索方法 | 对应宿主入口 | TMDB 接口 |
| --- | --- | --- |
| `multi` / `async_multi` | `TmdbApi.search_multiis` / `async_search_multiis` | `/search/multi` |
| `movies` / `async_movies` | `TmdbApi.search_movies` / `async_search_movies` | `/search/movie` |
| `tv_shows` / `async_tv_shows` | `TmdbApi.search_tvs` / `async_search_tvs` | `/search/tv` |
| `people` / `async_people` | `TmdbApi.search_persons` | `/search/person` |

这些方法只在调用方显式传入 `adult` 时才会拼上 `include_adult` 参数，而宿主自身从不传，
因此 TMDB 始终按默认的 `include_adult=false` 过滤成人内容。插件在这些方法外包装一层：

1. 调用方未指定 `adult` → 补上 `adult=True`（含 `search_multiis` 多类型搜索）；
2. 调用方显式指定 `adult`（True/False）→ 不覆盖，尊重调用方意图；
3. 插件关闭或停用 → 恢复原始方法，不向请求注入任何参数。

补丁的运行时状态与原始方法都挂在目标类上，因此插件模块被宿主重新加载后行为保持一致，
重复 `init_plugin()` 不会叠加包装层。

## 配置项

| 配置 | 默认 | 说明 |
| --- | --- | --- |
| 启用插件 `enabled` | **开** | 插件总开关，默认开启 |
| 识别时包含成人内容 `include_adult` | **开** | 置为 `true` 时注入 `include_adult=true`；关闭后即使插件启用也不注入 |

两个开关均默认开启，即安装后识别默认包含成人内容。

## 本地安装

1. 把本目录所在的本地插件仓库路径填入系统设置 `PLUGIN_LOCAL_REPO_PATHS`
   （插件仓库根目录需包含 `package.v3.json` 与 `plugins.v3/`，本仓库即为此结构）。
2. 在「插件」页的本地源中找到 `识别包含成人内容` 并安装。
3. 可选：设置 `PLUGIN_AUTO_RELOAD=true`，改动源码后自动重载。

## 注意

- 只影响 TMDB 搜索；豆瓣、Bangumi、IMDb 等其它数据源的过滤逻辑不受影响。
- TMDB 需要可用 API Key（`TMDB_API_KEY`），否则搜索本身就不会有结果。
- 请求 URL 会随注入的参数变化，因此注入后的结果与注入前的缓存互不干扰。
- 若宿主升级后调整了 `tmdbv3api` 目录结构或方法名，插件会记录错误日志并保持
  「未生效」状态，不会报错中断识别流程；此时需同步更新本文档上表中的方法名。
