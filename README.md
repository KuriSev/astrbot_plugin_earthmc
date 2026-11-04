# AstrBot Plugin: EarthMC

EarthMC Minecraft 服务器信息查询插件。支持 `/em` 命令和 LLM Agent 自然语言两种交互方式。

## 功能

- **服务器状态**: 在线人数、天气、月相、游戏时间
- **城镇/国家/玩家**: 详细信息查询
- **附近城镇**: 坐标周围领地分布
- **在线列表**: 当前在线玩家
- **Mystery Master**: 小游戏排行榜
- **销城风险分析**: 单镇变废墟时间、国家销城情况、国家/城镇废墟关注与每日推送
- **自动监控**: VP 阈值提醒、玩家上下线、城镇变动
- **市场交易**: 传送点交易信息板
- **地图截图**: 城镇/玩家/坐标的地图截图

## 命令

```
查询:
  /em status/vp/town/nation/player/online/nearby/location/quarter/mm
  /em mmo <技能>                 mcMMO 技能榜前 25 名
  别名: /t 城镇 · /n 国家 · /res 玩家 · /vp VP · /mctop mcMMO 榜

地图:
  /em map town <名>             城镇地图截图
  /em map player <名>           玩家位置截图
  /em map <x> <z>               坐标截图

销城分析:
  /em risk                   查看废墟关注状态
  /em risk town <名> / nation <名>
  /em risk town|nation add|del <名>

监控:
  /em vp <票数> / at add|del|reset|off / atline / dnd / status / off
  /em watch player add/del / town add/del / off

市场:
  /em market list / search / add / del
```

## 安装

1. 放入 AstrBot `data/plugins/` 目录
2. `docker restart astrbot`
3. 如需地图截图功能: `docker exec astrbot pip install Pillow`

## 配置

WebUI → 插件管理 → EarthMC，可调 8 个配置项。

## 数据

| 文件 | 内容 |
|------|------|
| `earthmc_watch.json` | 监控配置 |
| `earthmc_market.json` | 市场交易记录 |
| `earthmc_ruins_watch.json` | 废墟关注列表与快照 |

## 依赖

- `aiohttp`（AstrBot 预装）
- `Pillow`（可选，地图截图需要）

## License

AGPL-3.0
