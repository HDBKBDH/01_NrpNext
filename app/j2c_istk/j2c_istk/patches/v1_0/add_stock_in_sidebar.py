"""入库单 —— 加入侧栏（置顶）

背景：
  1. v16 的 Workspace JSON 导入路径随版本变化，靠文件导入不可靠，
     改用 Python patch 直接写 tabWorkspace Link。
  2. Workspace.type 是必填字段（默认 "Workspace"），缺失时 save 抛
     MandatoryError: [Workspace, J2C_ISTK]: type —— 一并修复。
"""

import frappe

WORKSPACE = "J2C_ISTK"
CARD_LABEL = "入库"
LINK_LABEL = "入库单"
LINK_TARGET = "Stock In"


def execute():
    if not frappe.db.exists("Workspace", WORKSPACE):
        print("  Workspace {0} 不存在，跳过".format(WORKSPACE))
        return

    # 修复必填字段
    if not frappe.db.get_value("Workspace", WORKSPACE, "type"):
        frappe.db.set_value("Workspace", WORKSPACE, "type", "Workspace")
        print("  + 修复 Workspace.type")

    ws = frappe.get_doc("Workspace", WORKSPACE)

    # 入库组始终置顶；其余链接去掉这两个后按原顺序保留。
    # 注意：判断「是否是我们要插入的行」必须同时看 type 和 link_to，
    # 否则用户已有的同名 label 会被误删。
    def is_ours(l):
        if l.type == "Card Break":
            return l.label == CARD_LABEL
        if l.type == "Link":
            return l.link_to == LINK_TARGET
        return False

    rest = [
        {"label": l.label, "type": l.type,
         "link_to": l.link_to, "link_type": l.link_type, "icon": l.icon}
        for l in ws.links
        if not is_ours(l)
    ]

    all_rows = [
        {"label": CARD_LABEL, "type": "Card Break"},
        {"label": LINK_LABEL, "type": "Link",
         "link_to": LINK_TARGET, "link_type": "DocType"},
    ] + rest

    added = len(ws.links) - len(rest)

    ws.links = []
    for i, r in enumerate(all_rows):
        r = {k: v for k, v in r.items() if v is not None}
        r["idx"] = i + 1
        ws.append("links", r)

    ws.save()
    frappe.db.commit()
    print("  ✓ 侧栏置顶：入库 / 入库单（新增 {0} 项，现有 {1} 项）".format(
        added, len(rest)))
