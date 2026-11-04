"""用户可见的固定文案（帮助文本、用法提示、操作关键字别名）。"""

HELP_TEXT = """🌍 EarthMC 查询
── 查询 ──
  status vp town nation player online nearby location quarter mm mmo
── 地图 ──
  /em map town <名>    城镇地图截图
  /em map player <名>  玩家位置截图
  /em map <x> <z>      坐标截图
── 路径点 ──
  /em wp              使用 /em wp help 查看子命令
── 分析 ──
  /em risk      使用 /em risk help 查看子命令
── 监控 ──
  /em vp        使用 /em vp help 查看子命令
  /em watch     使用 /em watch help 查看子命令
── 市场 ──
  /em market    使用 /em market 查看子命令
━━━━━━━━━━━━━━━━
别名: /t 城镇 · /n 国家 · /res 玩家 · /vp VP 提醒 · /mctop mcMMO 榜
也可直接 @bot 用自然语言询问"""

RISK_HELP = """销城分析:
  /em risk                       查看废墟关注状态
  /em risk town <名>             单镇评估（含变废墟时间）
  /em risk nation <名>           国家销城情况
  /em risk town add|del <名>     关注/取消关注城镇
  /em risk nation add|del <名>   关注/取消关注国家"""

MARKET_HELP = """市场交易:
  /em market list                   查看全部
  /em market sell add <t/n> <点> <价> <量> <物品>
      如 /em market sell add t mending 8 1 经验修补
  /em market buy add <t/n> <点> <价> <量> <物品>
  /em market trial add <t/n> <点>   记录试炼密室
  /em market <sell|buy> search <关键词>
  /em market <sell|buy|trial> del <id>
  /em market <sell|buy|trial>       查看对应类型
━━━━━━━━━━━━━━━━
也可直接告诉机器人: /t spawn mending有8g一本经验修补 / mending有试炼密室"""

WAYPOINT_HELP = """路径点:
  /em wp add <世界> <名称> <x> <y> <z>   记录（overworld主世界/nether地狱）
      如 /em wp add overworld 刷铁机 100 64 -200
  /em wp search <关键词> [世界]           搜索
  /em wp del <id>                        删除
  /em wp list [世界]                     查看全部"""

WATCH_HELP = """自动监控:
  /em watch player add <名>          添加玩家监控
  /em watch player del <名>          移除玩家监控
  /em watch player                   查看监控玩家列表
  /em watch town add <名>            添加城镇监控
  /em watch town del <名>            移除城镇监控
  /em watch town                     查看监控城镇列表
  /em watch off                      关闭所有（/em confirm 确认，/em cancel 取消）
  /em watch                          查看全部设置"""

VP_USAGE = ("❌ 用法: /em vp <票数> ... | at <add|del|reset|off> <QQ号> ... | "
            "atline <add|del|reset|off> <票数>... | dnd <开始> <结束> | status\n"
            "例如:\n"
            "  /em vp 500 200 100\n"
            "  /em vp at add 123456\n"
            "  /em vp at del 123456\n"
            "  /em vp at reset 123456 654321\n"
            "  /em vp at off\n"
            "  /em vp atline add 200\n"
            "  /em vp atline del 200\n"
            "  /em vp atline reset 200 100\n"
            "  /em vp dnd 23:00 07:30\n"
            "  /em vp dnd off\n"
            "  /em vp status")

# at / atline 的操作关键字别名
_OP_ALIASES = {
    "add": "add", "添加": "add",
    "del": "del", "delete": "del", "remove": "del", "删除": "del", "移除": "del",
    "reset": "reset", "重设": "reset",
}
