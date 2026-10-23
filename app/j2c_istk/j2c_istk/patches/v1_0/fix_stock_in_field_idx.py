"""Stock In —— 按 field_order 重排 DocField.idx

背景：Frappe 的表单渲染按 DocField.idx 排序，不看 DocType JSON 的 field_order。
改 JSON 后旧 idx 仍在数据库里，导致 Column Break 排到数据字段之后，
布局全部失效（字段竖排）。此patch 把 idx 按 field_order 重排。

幂等：每次按当前 field_order 重新计算。
"""

import json
import os

import frappe

DT_NAME = "Stock In"


def execute():
    if not frappe.db.exists("DocType", DT_NAME):
        print("  {0} 不存在，跳过".format(DT_NAME))
        return

    # field_order 只存在于 DocType JSON，不是 DocType 文档的属性
    app_path = frappe.get_app_path("j2c_istk")
    json_path = os.path.join(
        app_path, DT_NAME.lower().replace(" ", "_"), "doctype",
        DT_NAME.lower().replace(" ", "_"), DT_NAME.lower().replace(" ", "_") + ".json",
    )
    if os.path.exists(json_path):
        with open(json_path, encoding="utf-8") as f:
            order = json.load(f).get("field_order") or []
    else:
        # 退回按当前 idx 排序（至少保证顺序稳定）
        order = [r[0] for r in frappe.db.sql(
            """SELECT fieldname FROM `tabDocField`
               WHERE parent=%s ORDER BY idx""", (DT_NAME,))]

    if not order:
        print("  . 无法确定 field_order，跳过")
        return

    # 先删除 JSON 里已不存在的残留 DocField（改名后旧行会留在库里）
    wanted = set(order)
    stale = frappe.db.sql(
        """SELECT name FROM `tabDocField`
           WHERE parent=%s AND fieldtype IN ('Column Break','Section Break')
             AND fieldname NOT IN %s""",
        (DT_NAME, tuple(order)),
    )
    for (name,) in stale:
        frappe.db.delete("DocField", name)
    if stale:
        print("  - 删除 {0} 个残留布局字段".format(len(stale)))

    changed = 0
    for i, name in enumerate(order):
        where = {"parent": DT_NAME, "fieldname": name}
        if frappe.db.get_value("DocField", where, "idx") != i:
            frappe.db.set_value("DocField", where, "idx", i)
            changed += 1

    if changed:
        frappe.clear_cache(doctype=DT_NAME)
        frappe.db.commit()
        print("  ✓ 重排 {0} 个字段的 idx".format(changed))
    else:
        print("  . idx 已是正确顺序")

    # 验证
    rows = frappe.db.sql(
        """SELECT fieldname, fieldtype, idx FROM `tabDocField`
           WHERE parent=%s ORDER BY idx""",
        (DT_NAME,),
    )
    print("  渲染顺序（前 12）:")
    for r in rows[:12]:
        print("    {0:3d} {1:20s} {2}".format(r[2], r[0], r[1]))
