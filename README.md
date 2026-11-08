<div align="center">

# 🗺️ AstrBot 插件：EarthMC

[![AstrBot](https://img.shields.io/badge/AstrBot-%3E%3D4.0-27a7d8)](https://github.com/AstrBotDevs/AstrBot)
[![Version](https://img.shields.io/badge/version-v3.0.0-27a7d8)](CHANGELOG.md)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
[![Stars](https://img.shields.io/github/stars/KuriSev/astrbot_plugin_earthmc?style=flat&color=e9b949)](https://github.com/KuriSev/astrbot_plugin_earthmc/stargazers)
[![Last Commit](https://img.shields.io/github/last-commit/KuriSev/astrbot_plugin_earthmc)](https://github.com/KuriSev/astrbot_plugin_earthmc/commits/dev)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen)](https://github.com/KuriSev/astrbot_plugin_earthmc/pulls)

查询 EarthMC（Minecraft 服务器）的服务器状态、城镇、国家、玩家与在线列表，附带地图截图、市场信息板、销城风险预测与自动监控。

**支持 `/em` 命令与自然语言（LLM Agent）两种用法。**

</div>

## ✨ 能做什么

| 你想做的事 | 插件怎么帮你 |
|---|---|
| 快速查数据 | `/em status` 看在线人数/天气/月相，`/t` `/n` `/res` 查城镇、国家、玩家 |
| 看清势力分布 | 国家下属城镇、城镇成员、坐标附近领地、在线玩家列表 |
| 直接看地图 | 城镇 / 玩家位置 / 任意坐标生成网页地图截图 |
| 记交易信息 | 市场信息板记录「谁在哪个传送点卖/收什么、多少钱」 |
| 预判城镇兴衰 | 精确算出城镇何时变废墟或转让城主，关注国家/城镇后每天推送 |
| 盯住关键变化 | VP 进度提醒（可 @ 人、可免打扰）、玩家上下线与换镇、城镇人数/市长/开放状态变动 |
| 不想记命令 | 直接说「Teslin 的城主是谁」「Yukon 哪些城镇快变废墟」，由 LLM 调用工具完成 |

## 🚀 快速开始

1. **安装**：在 AstrBot WebUI → 插件市场搜索 **EarthMC** 直接安装；或把本目录放进 `AstrBot/data/plugins/`
2. **填 API Key（必填）**：游戏内执行 `/api key create` 获取（`/api key delete` 可删除已建的 key），粘贴到 WebUI → 插件管理 → EarthMC → 配置的 `api_key`。官方自 **2026-11-19** 起对所有 API 端点强制要求 key。
   **未填写时插件不工作**：查询命令会提示补配置，LLM 工具也不会注册
3. **依赖**：`aiohttp`（AstrBot 自带）、`Pillow`（地图截图用；缺了只是截图功能不可用）
4. **重载**：WebUI → 插件管理 → EarthMC → 重载（无需重启容器）

## 📝 命令一览

<details open>
<summary>查询</summary>

| 命令 | 说明 |
|---|---|
| `/em status` | 服务器状态：在线人数、天气、月相、游戏时间 |
| `/em vp` | 投票派对进度 |
| `/em town <名>` · `/t <名>` | 城镇详情 |
| `/em nation <名>` · `/n <名>` | 国家详情 |
| `/em player <名>` · `/res <名>` | 玩家详情 |
| `/em online` | 当前在线玩家 |
| `/em nearby <名>` | 城镇周边的领地分布 |
| `/em location <x> <z>` | 坐标属于哪个城镇/国家 |
| `/em quarter <名>` | 领地（Quarter）详情：类型、所有者、价格、体积 |
| `/em mm` | Mystery Master 排行榜 |
| `/em mmo <技能>` · `/mctop <技能>` | mcMMO 技能榜前 25 名（支持中文技能名） |
| `/em test` | 自检：当前 API Key 是否有效（会占用一次 mcMMO 查询配额） |
</details>

<details>
<summary>地图截图</summary>

| 命令 | 说明 |
|---|---|
| `/em map town <名>` | 城镇地图截图 |
| `/em map player <名>` | 玩家位置截图 |
| `/em map <x> <z>` | 任意坐标截图 |
</details>

<details>
<summary>销城风险</summary>

| 命令 | 说明 |
|---|---|
| `/em risk` | 查看关注的国家/城镇与窗口内条目（实时拉取最新数据） |
| `/em risk town <名>` | 单镇评估：变废墟/转让城主的精确时间、城主分支 |
| `/em risk nation <名>` | 国家维度：城镇按临近程度排序 |
| `/em risk town add\|del <名>` | 关注/取消关注城镇 |
| `/em risk nation add\|del <名>` | 关注/取消关注国家 |
</details>

<details>
<summary>监控</summary>

| 命令 | 说明 |
|---|---|
| `/em vp <票数> ...` | VP 多级提醒线 |
| `/em vp at add\|del\|reset\|off <QQ>` | 触发时 @ 的名单 |
| `/em vp atline add\|del\|reset\|off <票数>` | 哪些提醒线触发 @ |
| `/em vp dnd <起> <止>` | 免打扰时段（UTC+8，可跨午夜） |
| `/em vp status` / `off` | 查看 / 清除 VP 配置 |
| `/em watch player add\|del <名>` | 玩家监控（上下线、加入/离开城镇） |
| `/em watch town add\|del <名>` | 城镇变动监控 |
| `/em watch off` | 关闭全部监控（需 `/em confirm` 二次确认） |
</details>

<details>
<summary>市场与路径点</summary>

| 命令 | 说明 |
|---|---|
| `/em market list` / `search <关键词>` | 查看 / 搜索交易信息 |
| `/em market add <t\|n> <点> <价> <量> <物品>` | 添加一条（如 `/em market add t mending 8 1 经验修补`） |
| `/em market del <id>` | 删除条目 |
| `/em wp add <overworld\|nether> <名称> <x> <y> <z>` | 记录自定义路径点 |
| `/em wp search <关键词> [世界]` / `list` / `del <id>` | 搜索 / 查看 / 删除路径点 |
</details>

## 🤖 自然语言

不用记命令，直接对 Bot 说：

```
查一下 Teslin 的城主
Yukon 还有哪些城镇快变废墟
Fruitloopins 现在在哪个城
青金石哪里有卖
给 t spawn mending 记一条：8g 卖经验修补
画一张 Teslin 的地图
```

> 示例中的 `Teslin`（城镇）、`Yukon`（国家）、`Fruitloopins`（玩家）取自 [EarthMC 官方 API 文档](https://earthmc.net/docs/api) 的示例数据。

插件注册了 24 个 LLM 工具（`earthmc_town` / `earthmc_nation_risk` / `earthmc_market_search` / `earthmc_map_player` …），由 AstrBot 的 Agent 按需调用。

## ⚙️ 配置项

WebUI → 插件管理 → EarthMC → 配置：

| 键 | 默认 | 说明 |
|---|---|---|
| `api_key` | **必填** | EarthMC API key；未填时插件不工作 |
| `cache_ttl` | `30000` | GET 缓存时间（毫秒） |
| `http_timeout` | `10000` | 请求超时（毫秒） |
| `watch_interval` | `20000` | 监控轮询间隔（毫秒） |
| `town_check_interval` | `3` | 城镇变动每 N 次轮询检查一次 |
| `ruins_alert_days` | `7` | 废墟推送窗口（天） |
| `ruins_push_hour` | `18` | 每日推送时刻 · 时（**UTC+8**） |
| `ruins_push_minute` | `0` | 每日推送时刻 · 分（**UTC+8**） |

> 功能开关（VP、玩家/城镇监控等）按群/私聊保存在 `configs/` 下，可在 WebUI 的插件页面里按会话配置。

## 🏚 销城风险怎么算

- EarthMC 的失活判定是**即时**的：最后一名可见居民 42 天未上线即达到失活条件。
- 但「变废墟 / 转让城主」只在**每日结算点**执行：`最后一个居民 lastOnline + 42 天` 之后的第一个 **UTC 10:00（= UTC+8 18:00）**。
- 城主就是最后活跃的人 → 直接变废墟；否则**先转让城主**，城镇按最后一名活跃成员继续计时。
- 城主信息查不到（API 未返回）时按「未知」处理，不预测转让，并标注「数据不可用」。
- 关注列表以 **uuid** 存键，城镇改名不影响关注；每天到点推送窗口内的城镇，**推送前会强制刷新一次数据**，到点未成功推送不补发。

## 💾 数据文件

存放在 `AstrBot/data/plugin_data/astrbot_plugin_earthmc/`：

| 文件 | 内容 |
|---|---|
| `earthmc_watch.json` | 监控配置（VP 提醒线、@ 名单、免打扰；玩家/城镇以 uuid 为键） |
| `earthmc_ruins_watch.json` | 废墟关注列表与快照 |
| `earthmc_market.json` | 市场交易记录 |
| `configs/` | 按会话的功能开关 |

## 🔒 API Key 与隐私声明

> **官方公告**：自 **2026-11-19（周四）** 起，EarthMC 要求**所有 API 端点**都必须携带 API key。
> Key 免费，游戏内 `/api key create` 生成；限流规则不变。此举用于防范爬虫/AI 滥用，并允许官方吊销违规玩家的 key。
> 官方说明：[EarthMC API 文档 · API Keys](https://earthmc.net/docs/api#api-keys)

`api_key` 是 EarthMC 官方发放的身份凭据，本插件对它的处理方式如下：

- **用途唯一**：只随请求发送给官方接口 `https://api.earthmc.net/v4/`——普通查询放在 `X-API-Key` 请求头，mcMMO 排行榜按接口要求放在请求体 `key` 字段。不用于任何其它用途。
- **仅存本地**：保存在 AstrBot 的插件配置文件（`data/config/astrbot_plugin_earthmc_config.json`）中，与其它插件配置一样留在你自己的服务器上；插件不会把它写入聊天记录、插件数据目录或任何日志文件。
- **不会外流**：插件代码中没有任何统计、上报、遥测或第三方回传逻辑，不会把 key 发送到 EarthMC 官方以外的任何地址。
- **日志脱敏**：接口报错时日志只打印掩码形式（`前4位…后4位`），不输出完整 key。
- **可随时作废**：key 由你在游戏内 `/api key create` 生成，`/api key delete` 即可删除；分享配置截图或导出配置前，请自行遮蔽该字段。

> 该声明用于说明插件对凭据的处理方式，符合 EarthMC 关于 API 密钥的使用要求。

## ❓ 常见问题

**时间是什么时区？**
所有输出与配置（推送时刻、免打扰）都是 **UTC+8**。

**推送没收到？**
推送窗口内没有城镇时不会发；到点时机器人离线/异常则当次不补发，次日再来。可在群里先用 `/em risk` 确认关注列表和窗口内容。

**没填 API Key 会怎样？**
插件会停用全部查询：命令回复补配置的提示，LLM 工具不注册，后台监控也不会发起请求。填好后点「重载」即可恢复。

**Key 无效会怎样？**
官方从 2026-11-19 起对全部端点校验 key。接口返回 401/403 时，插件会提示「key 无效或查询失败」并给出重新生成的步骤，不会笼统显示成「查不到」。

## 🧱 目录结构（开发者）

```
main.py          # 入口与全部 @filter 装饰器
core/            # HTTP/缓存、落盘、文案、常量
commands/        # 命令实现（Mixin）
features/        # 业务能力：watch / risk / ruins_watch / market / map / mcmmo / waypoints
tools.py         # LLM FunctionTool 集合
webapi.py        # WebUI API
pages/           # WebUI 插件页面
```

## 📄 许可证

[AGPL-3.0](LICENSE)。

基于 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 插件模板开发，使用了其公开的插件接口；EarthMC 数据来自 [api.earthmc.net](https://api.earthmc.net/v4/) 与 [map.earthmc.net](https://map.earthmc.net/)。
