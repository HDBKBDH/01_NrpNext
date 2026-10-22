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

WORKSPACE = "贸易"

# Frappe v16 的 Workspace 没有 shortcuts 字段，
# 用 links 子表（Workspace Link）承载侧边栏入口。
# 每项：label=显示名，link_to=目标 DocType，type=DocType
# Workspace Link 子表的字段含义（很容易搞错）：
#   type      = "Link" | "Card Break"    ← 卡片内的一条链接，还是换一张卡
#   link_type = "DocType" | "Page" | "Report"
#   link_to   = 目标 DocType 名
# 传type="DocType" 会报「It should be one of "Link", "Card Break"」
SHORTCUTS = [
    {"label": "采购与拆解", "type": "Card Break"},
    {"label": "散件采购单", "link_to": "Loose Part Purchase",
     "type": "Link", "link_type": "DocType"},
    {"label": "拆解单", "link_to": "Disassembly Note",
     "type": "Link", "link_type": "DocType"},
    {"label": "物流与报关", "type": "Card Break"},
    {"label": "物流批次", "link_to": "Logistics Batch",
     "type": "Link", "link_type": "DocType"},
    {"label": "报关单", "link_to": "Customs Declaration",
     "type": "Link", "link_type": "DocType"},
    {"label": "退税证据包", "link_to": "Evidence Package",
     "type": "Link", "link_type": "DocType"},
    {"label": "商品轨迹", "link_to": "Item Transit Record",
     "type": "Link", "link_type": "DocType"},
    {"label": "库存与行情", "type": "Card Break"},
    {"label": "行情价历史", "link_to": "Market Price History",
     "type": "Link", "link_type": "DocType"},
    {"label": "用途变更", "link_to": "Purpose History",
     "type": "Link", "link_type": "DocType"},
    {"label": "工具", "type": "Card Break"},
    {"label": "标签打印", "link_to": "Label Print",
     "type": "Link", "link_type": "DocType"},
    {"label": "贸易设置", "link_to": "Trade Settings",
     "type": "Link", "link_type": "DocType"},
]

def _build_content():
    """工作台内容（Frappe block JSON → json.dumps 后赋值）

    v16 的 Workspace.content 有两个强制要求：
      1. workspace.py:614 sanitize_content 要 str/bytes
         → 传 list 报 TypeError: the JSON object must be str, bytes...
      2. workspace.py:106 validate 要 json.loads 后是 list
         → 传 HTML 字符串报 Content data shoud be a list
    所以必须 json.dumps(blocks) 传字符串，两边都满足。

    block 结构：
      header : {"type": "header", "text": "...", "size": 1|2}
      card   : {"type": "card", "header": "卡片名", "rows": [...]}
      doc    : {"type": "doc", "label": "...", "doctype": "...",
                "link_to": "..."}
      spacer : {"type": "spacer", "size": 1|2}
    """
    def header(text):
        return {"type": "header", "text": text, "size": 1}

    def card(title, entries):
        return {
            "type": "card",
            "header": title,
            "rows": [
                {
                    "type": "doc",
                    "label": label,
                    "doctype": doctype,
                    "link_to": doctype,
                }
                for label, doctype in entries
            ],
        }

    return [
        card(
            "采购与拆解",
            [
                ("散件采购单", "Loose Part Purchase"),
                ("拆解单", "Disassembly Note"),
            ],
        ),
        {"type": "spacer", "size": 1},
        card(
            "物流与报关",
            [
                ("物流批次", "Logistics Batch"),
                ("报关单", "Customs Declaration"),
                ("退税证据包", "Evidence Package"),
                ("商品轨迹", "Item Transit Record"),
            ],
        ),
        {"type": "spacer", "size": 1},
        card(
            "库存与行情",
            [
                ("行情价历史", "Market Price History"),
                ("用途变更", "Purpose History"),
            ],
        ),
        {"type": "spacer", "size": 1},
        card(
            "工具",
            [
                ("标签打印", "Label Print"),
                ("贸易设置", "Trade Settings"),
            ],
        ),
    ]


def execute():
    if frappe.db.exists("Workspace", WORKSPACE):
        ws = frappe.get_doc("Workspace", WORKSPACE)
        ws.module = "trade"
        ws.title = "二手贸易管理"
        ws.icon = "octicon octicon-package"
        ws.content = json.dumps(_build_content(), ensure_ascii=False)
        ws.public = 1
        ws.sequence = 10

        # 重建 links 子表。
        # 不要用 ws.set("links", ...)：Document.set 会遍历赋值，
        # 对 list/str 会报 "object does not support item assignment"。
        # 直接 ws.links = [] 后 append 最稳。
        ws.links = []
        for s in SHORTCUTS:
            row = {"label": s["label"], "type": s["type"]}
            if s.get("link_to"):
                row["link_to"] = s["link_to"]
                row["link_type"] = "DocType"
            ws.append("links", row)

        ws.flags.ignore_permissions = True
        ws.save(ignore_permissions=True)
        print(f"✓ 已更新 Workspace「{WORKSPACE}」")
        return

    ws = frappe.get_doc(
        {
            "doctype": "Workspace",
            "name": WORKSPACE,
            "label": WORKSPACE,
            "module": "trade",
            "title": "二手贸易管理",
            "description": "日本中古采购 · 拆解 · 报关 · 物流 · 销售",
            "icon": "octicon octicon-package",
            "sequence": 10,
            "public": 1,
            "content": json.dumps(_build_content(), ensure_ascii=False),
            "links": SHORTCUTS,
        }
    )
    ws.flags.ignore_permissions = True
    ws.insert(ignore_permissions=True)
    print(f"✓ 已创建 Workspace「{WORKSPACE}」")
