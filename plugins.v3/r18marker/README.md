# R18标志（R18Marker）

集中展示 MoviePilot 的**识别结果**并标记 **R18**，并可把 TMDB 绑定识别词**一键写入**自定义识别词。

## 三块能力

### 1. 识别结果清单

数据来自宿主稳定只读 SDK `app.sdk.queries`：

| 来源 | 查询 | 说明 |
| --- | --- | --- |
| 整理历史 | `list_transfer_history` | 整理流程的识别结果 |
| 下载历史 | `list_download_history` | 下载流程的识别结果 |
| 订阅 | `list_subscriptions` | 订阅的识别结果 |

页面（Vuetify JSON 模式，宿主内置 `PageRender` 渲染）逐条展示，右侧徽标：

| 徽标 | 颜色 | 含义 |
| --- | --- | --- |
| `R18` | 红（flat） | 判定为成人内容 |
| `R18 未判定` | 黄（tonal） | 无判定依据（非 TMDB 来源 / 关闭开关 / 查询失败） |
| `非 R18` | 绿（tonal） | 明确不是成人内容 |

### 2. R18 判定（v1.1.0 起优先用关键词）

1. **TMDB 关键词**：读 `/tv/{id}/keywords`、`/movie/{id}/keywords`，命中配置的关键词 ID（默认 **198385 = hentai**）即判为 R18；
   - 走宿主内置 TMDB 客户端的 `_request_obj("tv/{id}/keywords")`（`tv.py` 的 `_urls` 里就有 `keywords`）；
   - 该入口不可用时回退直连 HTTP（API Key / 域名读运行时设置 `settings.TMDB_API_KEY` / `TMDB_API_DOMAIN`）。
2. **回退**：关键词接口失败时读 TMDB 详情的 `adult` 字段。
3. 结果按 **7 天 TTL** 缓存（上限 2000 条）；非 TMDB 来源显示「未判定」，不伪造标记。

### 3. 识别词一键写入

内置 **205 条全量识别规则**（192 条 TMDB 绑定规则：191 条 `type=tv` + 1 条 `type=movie`；13 条通用清理规则），快照随插件版本发布。

| 接口 | 作用 |
| --- | --- |
| `GET /api/v1/plugin/R18Marker/identifiers/status` | 宿主现有条数 / 内置条数 / 已存在 / 待写入 |
| `GET /api/v1/plugin/R18Marker/identifiers/preview` | 预览合并结果（首尾各 8 条 + 总数，不写入） |
| `GET /api/v1/plugin/R18Marker/identifiers/apply` | **合并写入**宿主 `SystemConfigKey.CustomIdentifiers` |

写入行为：保留宿主已有识别词与顺序，只追加缺失的内置规则（按 `strip()` 后精确比对去重），**不删除、不覆盖**用户已有规则；重复点击是幂等的（第二次返回「已是最新」）。写入路径与宿主 `/config/identifiers` 端点同一个配置服务（`app.application.configuration.get_configured_system_config().set(...)`），因此配置变更事件与缓存保持一致。

> 识别词是**整表**存储的：如果之后你在 MoviePilot 界面里手工改过识别词，再点一次本插件的「写入识别词」即可把内置规则补回来，不会影响你手写的内容。

## 配置项

| 配置 | 默认 | 说明 |
| --- | --- | --- |
| 启用插件 `enabled` | **开** | 插件总开关 |
| 数据来源 `source` | `全部` | `全部` / `整理历史` / `下载历史` / `订阅` |
| 每类条数 `count` | `10` | 1–50 |
| 标志文字 `adult_text` | `R18` | 徽标文字 |
| 调用 TMDB 判定 `resolve_tmdb` | **开** | 关闭后不做外部查询，除宿主自带标记外都为「未判定」 |
| 优先用关键词判定 `use_keyword` | **开** | 先查关键词，再回退 `adult` 字段 |
| R18 关键词 ID `hentai_keyword_id` | `198385` | TMDB 关键词 hentai；可换成其它关键词 |
| 额外识别词 `extra_identifiers` | 空 | 每行一条，写入时追加在内置规则之后 |

## 其它接口

| 路径 | 方法 | 说明 |
| --- | --- | --- |
| `/api/v1/plugin/R18Marker/results` | GET | 识别结果清单（`total` / `r18` / `unknown` / `items[]`） |
| `/api/v1/plugin/R18Marker/refresh` | GET | 清空 R18 判定缓存 |

## 边界说明

- **标志只出现在插件自己的页面里**。MoviePilot 内置页面（媒体卡片、搜索/识别对话框、整理记录）没有插件扩展位，插件无法向其中注入 UI；要让内置页面也显示 R18，必须改 MoviePilot-Frontend 并重新构建替换 `FRONTEND_PATH`（默认 `/public`）。
- 不走 Vue 联邦模式：联邦需要 `dist/assets/remoteEntry.js` 构建产物（Node 环境），而 Vuetify JSON 模式由宿主前端直接渲染，交付即用。
- 只读取宿主数据；唯一的写操作是你主动点击「写入识别词」时对 `CustomIdentifiers` 的合并写入。

## 内置识别词快照的维护

全量规则的单一来源是 `识别规则/通用规则.txt`（通用部分）+ `识别规则-OVA-TMDB绑定.txt`（绑定部分），组装与注入脚本幂等：

```
识别规则/update_rules.ps1               # 新批次增量：解析 → 追写绑定规则
识别规则/build_full.ps1                 # 组装 识别规则-全量.txt（绑定 + 通用），并做四项自检
识别规则/inject_rules_into_plugin.ps1   # 把全量规则注入 plugins.v3/r18marker/__init__.py
```

`build_full.ps1` 的四个自检：① 每条绑定规则在全部文件名里只命中一个；② 绑定规则确实排在通用规则之前；③ 通用规则的正则全部可编译；④ 用一组「未绑定样例」模拟 MoviePilot 的处理效果。
`inject_rules_into_plugin.ps1` 会把注入的 Python 字面量还原后与源文件逐条比对（`mismatch=0` 才算通过）。

## 本地安装

1. 把仓库根目录（含 `package.v3.json` 与 `plugins.v3/`）填入系统设置 `PLUGIN_LOCAL_REPO_PATHS`。
2. 插件页 → 本地源 → 安装「R18标志」。
3. 打开插件详情：查看识别结果与 R18 标志；点「预览合并结果」「写入识别词（合并，不覆盖已有）」同步识别词。
