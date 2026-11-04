# Changelog

## v2.0.0

### 破坏性变更
- **移除全服扫描**：删除 `/em risk scan`、`/em risk list` 命令与 `features/scanner.py`；`/em risk nation` 不再读取扫描缓存，改为按国家实时计算城镇临近程度
- **移除扫描配置**：`scan_batch_size`、`scan_concurrency`、`deep_scan_max_residents`、`scan_hour`、`scan_minute`；WebUI 的「销城扫描」功能开关一并移除
- **移除 `/em risk ruin ...`**：关注操作并入 `risk` 本身，改为 `/em risk town|nation add|del <名称>`
- **监控数据改为 uuid 键**：`earthmc_watch.json` 的玩家/城镇、`earthmc_ruins_watch.json` 的国家/城镇均以 uuid 为键、名字仅作显示；首次检查/刷新时自动迁移。**迁移前已经改过名的实体会因旧名查不到而需要手动重新添加**

### 新增
- **变废墟时间预测**：按「最后一名居民 lastOnline + 42 天 → 下一个 UTC 00:00」精确计算；区分「城主失活即变废墟」与「先转让城主」两种分支，转让城主同样在 UTC 00:00 执行
- **`/em risk` 状态卡**：展示推送时刻、窗口天数、数据更新时间、关注国家/城镇与窗口内城镇（读快照，不联网）
- **废墟关注**：`/em risk town|nation add|del <名称>` 按群关注国家或单个城镇，新增后立即刷新并输出
- **每日定时推送**：每小时刷新快照，每天 `ruins_push_hour:ruins_push_minute`（UTC+8）推送一次「N 天内会变废墟或转让城主」的城镇；到点未推送不补发
- **配置项**：`ruins_alert_days`（窗口天数，默认 7）、`ruins_push_hour`（默认 18）、`ruins_push_minute`（默认 0）
- **uuid 稳定标识**：玩家监控、城镇监控、国家/城镇关注全部改为 uuid 键，改名不再导致监控失效；玩家的城镇基线用 `town_uuid` 比较

### 变更
- `/em risk town` 输出简化：只显示 UTC+8 时间（带年份）、剩余天数、城主、开放/封闭状态；不再显示风险等级与逐人剩余天数
- `/players` 查不到的居民不参与 `max` 计算；**城主查不到时按“未知”处理**，不预测转让并标注 `（数据不可用）`

### 修复
- **批量查询被 API 截断**：单次 `/towns`、`/players` 查询超过约 100 个会被截断，导致国家城镇只显示一部分、居民数据缺失被误判为 inactive；现统一按 50 个一批
- **城主数据不可用被误判为失活**：关闭 API 的城主曾产生大量「转让城主·剩 0 天」误报，现按未知处理

## v1.15.1

### 新增
- **顶层别名 `/mctop`**：`/mctop <技能>` 等价 `/em mmo <技能>`，直接查 mcMMO 技能榜，不必先打 `/em`；参数只取首个词（与 `/t` `/n` `/res` 一致），多余文本静默截断；与 `/em` 共享 `commands` 功能开关

### 变更
- `/em` 帮助文本（`HELP_TEXT`）别名行补充 `/mctop mcMMO 榜`
- README 命令清单补充 `/em mmo <技能>` 与顶层别名说明
- **代码结构分层**：`main.py` 拆为 `core/`（`api` HTTP 缓存、`store` 落盘、`texts` 文案、`constants` 共享常量）、`commands/`（命令实现 Mixin）、`features/`（业务能力）、`webapi.py`（WebUI API）；`main.py` 1840 → 353 行，只保留 `@filter` 装饰器方法、`cmd_em` 分发与生命周期。**命令输出与行为不变**
- **销城风险计算独立**：`_calc_risk` / `_nation_risk` / `_list_members` / `_list_nation_towns` 及 4 个风险类 Tool 从 `tools.py` 移入 `features/risk.py`，命令层与全服扫描器不再反向依赖 LLM 工具层；`INACTIVE_DAYS` 移入 `core/constants.py`（`tools.py` 807 → 438 行）

## v1.15.0

### 新增
- **顶层命令别名**：`/vp`（= `/em vp`）、`/res`（= `/em player`）、`/t`（= `/em town`）、`/n`（= `/em nation`），与 `/em` 共享功能开关
- **参数自动截断**：`/t` `/n` `/res` 只取首个词作名字（`/t 北京 在哪` 正常查北京）；`/vp` 遇到格式不符的 token 即停止解析（`/vp status 多余`、`/vp 500 abc` 等不再报错），静默忽略多余内容
- **玩家城镇变动监控**：被监控玩家加入/离开/换城镇时自动提醒；添加玩家时记录当前城镇作为基线（避免误报）
- **mcMMO 排行榜查询**：`/em mmo <技能>` 输出某技能排行榜前 25 名；新增 `api_key` 配置项（游戏内 `/api key create` 获取）；LLM 工具 `earthmc_mcmmo_top`
- **技能名中英兼容**：支持中文技能名（如 钓鱼/挖矿/炼药/驯兽/总等级），LLM 按用户措辞回显技能名；请求前按官方技能白名单校验，杜绝非法传入
- **国家详情增强**：国家加成（nationBonus）、禁运、条约、Discord 链接
- **城镇详情增强**：传送点（warps）、Discord 链接
- **`/em watch off` 二次确认**：关闭本群全部监控改为两步——发起人 30 秒内 `/em confirm` 确认执行、`/em cancel` 取消；中途执行其它命令自动取消
- **`vp at` / `atline` 增量操作**：支持 `add`（追加）/ `del`（移除）/ `reset`（重设）/ `off`（清空），并支持中文关键字（添加/删除/重设）；at 与 atline 交互统一
- **代码模块化**：mcMMO 查询独立为 `mcmmo.py`

### 变更
- `/em` 帮助文本（`HELP_TEXT`）监控段统一为「使用 /em vp help 查看子命令」风格（与 `/em wp`、`/em risk`、`/em market` 一致），子命令详情改由 `/em vp help`、`/em watch help` 呈现
- **VP 提醒移至独立顶层 `/em vp`**（原 `/em watch vp ...` 全部迁移）：裸 `/em vp` 查询投票派对进度、`/em vp help` 看用法、`/em vp status` 看配置；配置仅限群聊
- `vp at` / `atline` 改为**关键字式**：`/em vp at <QQ号>` 裸数字写法失效，须写 `at add|del|reset|off`；留空（`/em vp at`）显示当前配置
- mcMMO 命令精简为 `/em mmo <技能>`；移除 `/em mmorank`（不再支持按玩家查排名，"某技能第 N 名是谁"由 LLM 从返回榜单读出）
- mcMMO 删除翻页：API 每个技能仅返回前 25 名，一次全量输出
- `/em vp` 输出精简为单行（去进度条/分隔线）

### 修复
- mcMMO 榜单在**自然语言路径**被 LLM 转述成一行：工具 description 补充"整段原样输出、保留换行、不要合并成一行"的格式指令；表头规范为 `排行榜（前 N 名）`
- **名称大小写统一**：查询侧本就不敏感（实测 API 不区分大小写），修复的是比较与显示——watch 增删的 6 处大小写敏感比较（含**城镇重复 add 会重置基线导致漏报一轮变动**）、通知文案改用服务端规范名、存量配置的玩家/城镇 key 自动纠正为规范大小写
- `_cmd_watch_town` 的 `from .tools import post` 改为 `from .api import post`（原写法依赖 tools 模块恰好 re-export，较脆弱）
- 国家禁运/条约解析：API 实际返回 dict（`{own,against}`、`{active:[...]}`）而非列表，原解析崩溃，现已兼容
- mcMMO API key 请求机制：按官方文档将 key 放入请求体 `key` 字段（原误用 header 导致 401）
- API 请求 HTTP 错误处理：非 2xx 响应返回明确状态日志，不再误报 `Expecting value` JSON 解析错误
- mcMMO-top 接口限流：加 3 分钟结果缓存，避免触发每 key 2 分钟限流
- `/em confirm`/`/em cancel` 群聊判定修正：仅认 `group_id`，私聊正确提示"仅在群聊中可用"（原 `session_id` 兜底使判断失效）

## v1.14.0

### 新增
- **VP 触发时 @ 名单**：`/em watch vp at <QQ号> ...`，VP 到达预警线时 @ 指定成员
- **VP @ 按提醒线独立标记**：`/em watch vp atline <票数> ...`，仅在标记的提醒线触发 @（默认不 @；标记不在提醒线中的票数时拒绝）
- **VP 免打扰时段**：`/em watch vp dnd <开始> <结束>`（UTC+8，支持跨午夜），免打扰期间只发文本不 @
- **WebUI 防误操作**：新建配置改为浮窗输入 + 冲突检测；功能开关与 VP 设置未保存更改提示（"⚠ 未保存"徽标，切换/刷新/关页拦截）；每行提醒线「触发时 @」勾选；身份编辑区只读
- **WebUI 删除二次确认**：删除玩家/城镇/配置前弹出确认浮窗
- **WebUI VP 设置独立分区**：VP 提醒从"监控设置"中拆出为独立分区（提醒线 / @ 名单 / 免打扰），新增后端 `vp/status`、`vp/save`、`vp/off` API；"清除提醒线"对应 `/em vp off`，"关闭玩家/城镇监控"不再连带清除 VP

### 变更
- VP @ 从"所有提醒线都 @"改为"每线独立标记"（`atline`），未标记默认不 @——旧配置需重新用 `atline` 标记
- 移除 WebUI 玩家列表在线/离线、城镇列表人数/块数展示（后端监控检测不受影响）
- 移除 watch 输出中的检测间隔行

### 修复
- WebUI 原生 `confirm()` 在 AstrBot 受限 iframe 中被禁用导致删除/确认无响应，改为页内自定义确认浮窗

## v1.13.1

### 修复
- WebUI 添加监控后 watch.json 缺少 `umo`，导致新群监控轮询被跳过；现按 `qq-bot:GroupMessage/FriendMessage:{id}` 格式自动补全

## v1.13.0

### 新增
- **设置页面合并**：功能开关与监控设置（VP 阈值/玩家/城镇）整合为单一 Plugin Page
- **Watch 管理 API**：`watch/groups`、`watch/status`、`watch/vp/save`、`watch/player/add/del`、`watch/town/add/del`、`watch/off`

### 变更
- 移除独立的 `pages/watch/` 页面，并入 `pages/configs/`

## v1.12.1

### 修复
- **market add 解析**：`split(maxsplit=2)` 导致 `trial/sell/buy add` 丢失传送点后的参数
- **map 坐标解析**：`/em map <x> <z>` 坐标被拆分导致截图失败

## v1.12.0

### 新增
- **试炼密室记录**：`/em market trial add <t/n> <点>`，LLM 工具 `earthmc_trial_add` / `earthmc_trial_list`
- **路径点记录**：`/em wp add <世界> <名称> <x> <y> <z>`，区分主世界/地狱（下界），LLM 工具 `earthmc_waypoint_add` / `earthmc_waypoint_search`
- **市场分类型**：`/em market sell` / `buy` / `trial` 三类管理，命令可区分出售/收购
- **WebUI 配置管理**：`pages/configs/` 按群/私聊独立管理功能开关

## v1.11.0

### 新增
- **地图截图**：`/em map town <名>`、`/em map player <名>`、`/em map <x> <z>`
- **LLM 地图工具**：`earthmc_map_town`、`earthmc_map_player`、`earthmc_map_location`，支持自然语言截图
- **城镇成员变动追踪**：watch 监控人口变化时输出具体加入/退出的玩家名

### 修复
- **VP 误报 0**：scan 高并发时 API 返回不完整导致 VP 检测报 0，现跳过不完整响应
- **watch 配置原子写入**：防止容器重启时 JSON 文件截断损坏
- **watch 竞态条件**：命令处理与轮询同时修改配置不再互相覆盖
- **player watch 状态判断**：`state.get("online")` 无默认值导致误判

### 变更
- VP 数据采集独立为 `earthmc_vp_collector` 项目，脱离 AstrBot

## v1.10.0

### 新增
- VP 监测数据采集（后移至独立项目）
- 销城风险全服扫描
- 市场交易信息板
- 城镇成员遍历、国家城镇遍历 LLM 工具

### 修复
- 多项 watch 监控稳定性修复
