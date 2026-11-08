# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

本插件的**实现细节统一维护在工作区的 [`../docs/earthmc-plugin.md`](../docs/earthmc-plugin.md)**，本文件只做指针 + 高频操作，避免两份副本漂移。

- 部署拓扑、SSH、端口、SnowLuma、多开 QQ → [`../CLAUDE.md`](../CLAUDE.md)
- AstrBot 插件开发 API 速查（FunctionTool / filter / Plugin Pages）→ [`../docs/astrbot-dev-reference.md`](../docs/astrbot-dev-reference.md)
- 本插件命令体系、模块划分、缓存、配置项、mcMMO、watch/VP、废墟预测与关注、WebUI Pages → [`../docs/earthmc-plugin.md`](../docs/earthmc-plugin.md)

## 常用命令

没有构建、测试或 lint 步骤（纯插件源码，无 pyproject / 测试套件）。开发循环就是「改本地 → 上传 → WebUI 重载插件」：

```bash
# 本地 → 服务器（本机 D:\MyProject\astrbot\astrbot_plugin_earthmc\ 为 Git 仓库，分支 master）
# 上传到 ~/astrbot/data/plugins/astrbot_plugin_earthmc/

ssh astrbot
sudo find ~/astrbot/data/plugins/astrbot_plugin_earthmc -type d -name __pycache__ -exec rm -rf {} +   # 必做，否则加载旧字节码
# 然后在 AstrBot WebUI(6185) → 插件管理 → EarthMC → 重载
docker logs -f astrbot | grep -i earthmc
```

`pages/` 静态资源改动只需刷新浏览器；改 `.py` 后走 WebUI 重载。**日常用重载，不要 `docker compose up -d` 重建**——插件依赖装在容器层，重建后会丢；`docker restart astrbot` 只在重载无效时兜底。

提交在本仓库（`origin` = `KuriSev/astrbot_plugin_earthmc`）里做；`metadata.yaml` 的 `version` 与 `CHANGELOG.md` 同步维护。

**分支模型：`dev` 是唯一开发分支，`master` 只做发布快照。** GitHub 默认分支是 `master`（对外展示最新发布），日常开发全部提交到 `dev`；发版时才把 `master` fast-forward 到 `dev` 并推送。

```bash
# 日常
git push origin dev

# 发版（版本号/CHANGELOG 提交之后）
git checkout master && git merge --ff-only dev
git push origin master
git checkout dev
```

`master` 不允许单独提交（只能 fast-forward），避免与 `dev` 分叉。

## 架构要点

- **双入口**：`main.py` 的 `/em` 命令族（含顶层别名 `/vp` `/t` `/n` `/res`）与 `tools.py` 的 LLM FunctionTool，两者共享 `core/api.py` 的请求/缓存层。
- **目录分层**：`main.py`（入口 + 装饰器）→ `commands/`（命令实现 Mixin）→ `features/`（业务能力）→ `core/`（HTTP、落盘、文案）。**`@filter.*` 只能写在 `main.py`**，AstrBot 按 `handler.__module__` 绑定实例，搬走即静默失效。
- **`features/watch.py`**：后台监控（VP 阈值 / 玩家上下线与城镇变动 / 城镇变动），状态在 `earthmc_watch.json`，按群隔离。**玩家与城镇都以 uuid 为键、名字只作显示**（`/online`、`/players`、`/towns` 均返回 uuid，且 `query` 接受 uuid）。
- **`features/ruins_watch.py`**：废墟关注（国家/城镇，同样 uuid 键）。每 60 秒 tick、**每小时刷新快照**、**每天 `ruins_push_hour:ruins_push_minute`（UTC+8）推送前再强制刷新一次**再推窗口内城镇；到点未发不补发。裸 `/em risk` **实时拉数据出状态卡（只读，不写回快照）**，查不到的城镇沿用上次快照并标注。`RuinsChecker.start()` 在 `__init__` 启动——`on_astrbot_loaded` 重载后不会再触发，只放那里会让刷新/推送静默停摆。
- **`features/risk.py`**：变废墟时间计算（`analyze_ruins`：最后居民 lastOnline + 42 天 → 下一个**每日结算点 UTC 10:00 = UTC+8 18:00**；城主两种分支）与 `/em risk town` 渲染。日界常量是 `DAY_BOUNDARY_HOUR_UTC = 10`，别改回 UTC 00:00（由 `timestamps.ruinedAt` 统计确认）。
- **全服扫描已移除**：没有 `scanner.py`、`/em risk scan`、`/em risk list`，risk 只针对指定城镇/国家。
- **API 批量上限**：`/towns`、`/players` 单次 query 超过约 100 会被截断，批量请求一律用 `core/api.py::post_chunked`（50/批）。
- **`features/mcmmo.py`** 独立于主流程，需 `api_key`（放**请求体**而非 header，技能名大写白名单），结果缓存 180s。
- **命名**：查询不区分大小写、直接透传；**比较两侧都 `.lower()`，显示用服务端规范名**；监控/关注的**存储键是 uuid**。细节见 `../docs/earthmc-plugin.md`「名称大小写约定」。
- **坐标**：API 的 `coordinates.spawn` 是小数，展示一律转方块坐标——**向下取整**（`-3829.3 → -3830`），统一用 `core/utils.py::fmt_coord` / `fmt_coord_pair`，别用 `int()`（负数是向零截断，会差一格）。
- **时区**：`ruins_push_hour` / `ruins_push_minute` / `/em vp dnd` 一律 UTC+8；容器时钟是 UTC，用 `datetime.now(timezone.utc) + timedelta(hours=8)`，别用裸 `datetime.now()`。
