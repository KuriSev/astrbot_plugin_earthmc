# Changelog

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
