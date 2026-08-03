# Changelog

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
