"""创建 Desk 工作台「贸易」（兜底）

主路径是 trade/workspace/trade/trade.json —— bench migrate 会自动 import，
这是 Frappe 官方机制。

本 patch 只在 JSON import 失败时兜底（比如 JSON 语法错误）。
两个踩过的坑：
1. 不能靠 hooks.json_files——Frappe v16 会把不在 doctype 目录的
   Workspace 当 orphan 删掉（migrate 日志：Removing orphan Workspaces）
2. v16 的 Workspace 没有 shortcuts 字段，用 links 子表（Workspace Link）
   承载侧边栏入口
   另外 Workspace 有必填的 module 字段（app 级 Workspace 专用）
3. content 必须是 JSON **字符串**：
   - workspace.py:614 sanitize_content 要 str/bytes（传 list 报
     TypeError: the JSON object must be str, bytes or bytearray, not list）
   - workspace.py:106 validate 要 json.loads 后是 list
   所以：json.dumps(blocks) 传字符串，两边都满足
4. 不要用 doc.set(field, value) 改 Table / Code 字段——
   Document.set 会遍历赋值，对 list/str 报
   "TypeError: 'str' object does not support item assignment"。
   直接 doc.field = [] 然后 doc.append() 更稳。
"""

import json

import frappe

# Workspace 名（业务统一命名 J2C_ISTK）
WORKSPACE = "J2C_ISTK"

# 旧名（重命名前建的），存在就删掉
LEGACY_WORKSPACES = ["贸易"]

# 卡片分组：name 是 Card Break 的 label，entries 是它下面的链接
CARD_GROUPS = [
    ("采购与拆解", ["散件采购单", "拆解单"]),
    ("物流与报关", ["物流批次", "报关单", "退税证据包", "商品轨迹记录"]),
    ("库存与行情", ["行情价历史", "用途变更"]),
    ("工具", ["标签打印", "贸易设置"]),
]

# 展示名 → DocType 名
DOCTYPE_MAP = {
    "散件采购单": "Loose Part Purchase",
    "拆解单": "Disassembly Note",
    "物流批次": "Logistics Batch",
    "报关单": "Customs Declaration",
    "退税证据包": "Evidence Package",
    "商品轨迹记录": "Item Transit Record",
    "行情价历史": "Market Price History",
    "用途变更": "Purpose History",
    "标签打印": "Label Print",
    "贸易设置": "Trade Settings",
}

# Frappe v16 的 Workspace 没有 shortcuts 字段，
# 用 links 子表（Workspace Link）承载侧边栏入口。
#
# Workspace Link 子表的字段含义（很容易搞错）：
#   type      = "Link" | "Card Break"    ← 卡片内的一条链接，还是换一张卡
#   link_type = "DocType" | "Page" | "Report"
#   link_to   = 目标 DocType 名
# 传 type="DocType" 会报「It should be one of "Link", "Card Break"」
#
# 注意：content 里的 card block 通过 card_name 匹配 links 里
# type="Card Break" 的 label，所以两边必须一致。


def _build_links():
    """从 CARD_GROUPS 生成 links 子表数据"""
    links = []
    for group_name, entries in CARD_GROUPS:
        links.append({"label": group_name, "type": "Card Break"})
        for label in entries:
            links.append({
                "label": label,
                "link_to": DOCTYPE_MAP[label],
                "link_type": "DocType",
                "type": "Link",
            })
    return links


def _build_content():
    """工作台内容（Frappe v16 的 block 格式）

    v16 的正确用法（踩了 3 轮才对）：
      content block: {"id": "<hash>", "type": "<block>", "data": {...}}

      卡片内容用 "card" block，data.card_name 指向 links 子表里
      type="Card Break" 的 label：
        {"id":"c1","type":"card","data":{"card_name":"采购与拆解","col":4}}

      前端解析（block.js: make()）：
        this.config.page_data[block + "s"].items.find(
            obj => unescape_html(obj.label) == unescape_html(__(block_name)))
      → card 走 page_data["cards"].items（Card Break 及其 links）
      → shortcut 走 page_data["shortcuts"].items（顶层 shortcuts，不分组）

      所以：
        - 想要"分组卡片" → content 用 card block + links 里 Card Break
        - 想要"平铺快捷方式" → content 用 shortcut block
      旧格式 {"type":"card","header":"...","rows":[...]} 会报
      "AttributeError: 'NoneType' object has no attribute 'lower'"

      content 必须是 JSON 字符串（json.dumps 后传）：
        workspace.py:614 sanitize_content 要 str/bytes
        workspace.py:106 validate 要 json.loads 后是 list
    """
    def card(name, idx, col=4):
        return {
            "id": f"j2ccard{idx:03d}",
            "type": "card",
            "data": {"card_name": name, "col": col},
        }

    return [
        card(name, i)
        for i, (name, _entries) in enumerate(CARD_GROUPS, 1)
    ]


def execute():
    # 清理旧名 Workspace（重命名前建的）
    for old in LEGACY_WORKSPACES:
        if old != WORKSPACE and frappe.db.exists("Workspace", old):
            frappe.delete_doc(
                "Workspace", old, force=True, ignore_permissions=True
            )
            print(f"✓ 删除旧 Workspace「{old}」")

    if frappe.db.exists("Workspace", WORKSPACE):
        ws = frappe.get_doc("Workspace", WORKSPACE)
        ws.module = "J2C_ISTK"
        ws.title = "J2C_ISTK"
        ws.icon = "octicon octicon-package"
        ws.content = json.dumps(_build_content(), ensure_ascii=False)
        ws.public = 1
        ws.sequence = 10

        # 重建 links 子表。
        # 不要用 ws.set("links", ...)：Document.set 会遍历赋值，
        # 对 list/str 会报 "object does not support item assignment"。
        # 直接 ws.links = [] 后 append 最稳。
        ws.links = []
        for row_data in _build_links():
            ws.append("links", dict(row_data))

        # 兜底：Workspace Link.link_type 为 None 时，desktop.py:257 会报
        # "AttributeError: 'NoneType' object has no attribute 'lower'"
        # （is_item_allowed 里 item_type.lower()）
        # 踩过的坑：Workspace JSON 的 links 里写了 link_type，
        # 但 migrate 导入后数据库里是 NULL —— 所以这里显式补。
        fixed = frappe.db.sql(
            """
            UPDATE `tabWorkspace Link`
            SET link_type = 'DocType'
            WHERE parent = %s AND type = 'Link'
              AND (link_type IS NULL OR link_type = '')
            """,
            (WORKSPACE,),
        )
        if fixed:
            print(f"✓ 修复 {fixed} 行 link_type → DocType")

        ws.flags.ignore_permissions = True
        ws.save(ignore_permissions=True)
        print(f"✓ 已更新 Workspace「{WORKSPACE}」")
        return

    ws = frappe.get_doc(
        {
            "doctype": "Workspace",
            "name": WORKSPACE,
            "label": WORKSPACE,
            "module": "J2C_ISTK",
            "title": "J2C_ISTK",
            "description": "日本中古采购 · 拆解 · 报关 · 物流 · 销售",
            "icon": "octicon octicon-package",
            "sequence": 10,
            "public": 1,
            "content": json.dumps(_build_content(), ensure_ascii=False),
            "links": _build_links(),
        }
    )
    ws.flags.ignore_permissions = True
    ws.insert(ignore_permissions=True)
    print(f"✓ 已创建 Workspace「{WORKSPACE}」")
