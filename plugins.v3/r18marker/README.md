# R18标志（R18Marker）

把 MoviePilot 里分散的**识别结果**集中到一个插件页面，并为成人内容条目显示 **R18** 标志。

## 页面内容

数据全部来自宿主稳定的只读查询 SDK `app.sdk.queries`：

| 来源 | 使用的查询 | 说明 |
| --- | --- | --- |
| 整理历史 | `list_transfer_history` | 整理流程的识别结果（标题/年份/类型/日期/媒体身份） |
| 下载历史 | `list_download_history` | 下载流程的识别结果 |
| 订阅 | `list_subscriptions` | 订阅的识别结果 |

页面为 Vuetify JSON 模式（`get_render_mode()` 默认 `vuetify`），由 MoviePilot 前端内置的
`PageRender` 渲染，无需构建前端资源。每行一个卡片，右侧徽标：

| 徽标 | 颜色 | 含义 |
| --- | --- | --- |
| `R18` | 红（error，flat） | 判定为成人内容 |
| `R18 未判定` | 黄（warning，tonal） | 没有可用的判定依据（非 TMDB 来源、未开开关或查询失败） |
| `非 R18` | 绿（success，tonal） | 明确不是成人内容 |

页面顶部显示 `共 N 条 / R18 M 条 / 未判定 K 条`，底部有「清空判定缓存并重新判定」按钮。

## R18 判定依据

这些只读快照**只带媒体身份**（`media_source` + `media_id`），不含成人标记，因此判定规则是：

1. 快照本身带 `adult` 布尔值 → 直接采用（兼容宿主未来新增该字段）；
2. 媒体身份为 **TMDB**（`media_source = "themoviedb"`，等价 `MediaSource.TMDB`）且开关打开 →
   用宿主内置 TMDB 客户端按 ID 读取详情，取 `adult` 字段；
3. 其它来源（豆瓣 / Bangumi / IMDb / AniList / TVDB 等）没有等价字段 → 显示「未判定」，**不猜测、不伪造**。

判定结果按 **7 天 TTL** 缓存在插件数据里（上限 2000 条），因此页面首次加载会对未缓存的
TMDB 条目发起查询，之后直接命中缓存。TMDB 查询失败（网络、限流、无效 ID）只记为未判定，
不影响页面其它内容。

## 配置项

| 配置 | 默认 | 说明 |
| --- | --- | --- |
| 启用插件 `enabled` | **开** | 插件总开关 |
| 数据来源 `source` | `全部` | `全部` / `整理历史` / `下载历史` / `订阅` |
| 每类条数 `count` | `10` | 1–50，每类来源读取并展示的条数 |
| 标志文字 `adult_text` | `R18` | 徽标文字，可按习惯改成 `R18+`、`成人` 等 |
| 调用 TMDB 判定 `resolve_tmdb` | **开** | 关闭后不做任何外部查询，除宿主自带标记外都为「未判定」 |

## 插件 API

| 路径 | 方法 | 说明 |
| --- | --- | --- |
| `/api/v1/plugin/R18Marker/results` | GET | 返回识别结果清单：`total` / `r18` / `unknown` / `items[]` |
| `/api/v1/plugin/R18Marker/refresh` | GET | 清空 R18 判定缓存，返回 `success` |

页面的刷新按钮就是通过页面 JSON 的 `events` 调用 `plugin/R18Marker/refresh`，调用完成后
前端会自动重新拉取页面数据。

## 边界说明

- **本插件的标志只出现在插件自己的页面里。** MoviePilot 的内置页面（媒体卡片、搜索/识别
  对话框、整理记录等）没有插件扩展位，插件无法向其中注入 UI；若要让内置页面也显示 R18，
  必须改 MoviePilot-Frontend 前端源码并重新构建替换 `FRONTEND_PATH`（默认 `/public`）。
- 不走 Vue 联邦模式的原因：联邦需要 `dist/assets/remoteEntry.js` 构建产物（需要 Node 环境），
  而 Vuetify JSON 模式由宿主前端直接渲染，交付即可用。
- 只读取宿主数据，不修改任何媒体、订阅或整理记录。

## 本地安装

1. 把本仓库根目录（含 `package.v3.json` 与 `plugins.v3/`）填入系统设置
   `PLUGIN_LOCAL_REPO_PATHS`。
2. 插件页 → 本地源 → 安装「R18标志」。
3. 打开插件详情（卡片上的详情按钮）即可看到识别结果清单。
