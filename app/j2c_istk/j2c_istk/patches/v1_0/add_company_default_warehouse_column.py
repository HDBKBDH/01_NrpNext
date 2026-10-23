"""让 Company 列表显示「默认仓库」列

需求（用户确认）：
  「在 Company 列表加『默认仓库』列，直接看到并跳转修改」
  语义：每个 Company 各自的默认仓（7 个值）

现状问题：
  Company.default_warehouse 是 ERPNext 标准字段，可编辑，
  但 in_standard_filter = 0 → 列表页不显示这一列，
  而且它藏在「库存与生产」tab 下方的「仓库默认设置」section，
  7 个 Company 哪个默认仓是什么完全看不出来。

做法（比 Custom Field 更干净）：
  用 Property Setter 把标准字段 default_warehouse
  加上 in_list_view = 1 —— 直接显示原字段，零重复存储。

  ERPNext 自己就这么干（实测）：
    ('Item', 'item_group', 'in_list_view', '1')
    ('Item', 'stock_uom',  'in_list_view', '1')
  → 说明这是官方支持的用法。

踩过的坑：
  一开始想加 Custom Field（Virtual 类型），
  但 v16 的 Custom Field 不接受 fieldtype='Virtual'
  （报错："Field Type cannot be \"Virtual\""），
  合法类型里最接近的是 'Read Only'（需要真实存储，会重复数据）。
  → 改用 Property Setter，直接改标准字段的显示属性，零数据重复。
"""

import frappe


def execute():
    field = "default_warehouse"
    doctype = "Company"

    # 1. 确保字段有 in_list_view
    if not frappe.db.exists("Property Setter", {
        "doc_type": doctype, "field_name": field, "property": "in_list_view"
    }):
        doc = frappe.get_doc(
            {
                "doctype": "Property Setter",
                "doc_type": doctype,
                "doctype_or_field": "DocField",
                "field_name": field,
                "property": "in_list_view",
                "value": "1",
                "property_type": "Check",
            }
        )
        doc.flags.ignore_permissions = True
        doc.insert(ignore_permissions=True)
        print(f"✓ Company.{field} → in_list_view = 1")
    else:
        frappe.db.set_value(
            "Property Setter",
            {"doc_type": doctype, "field_name": field, "property": "in_list_view"},
            "value",
            "1",
            update_modified=False,
        )
        print(f"= Company.{field} 的 in_list_view 已是 1")

    # 2. 同时加 in_standard_filter（可按默认仓筛选）
    if not frappe.db.exists("Property Setter", {
        "doc_type": doctype, "field_name": field, "property": "in_standard_filter"
    }):
        doc = frappe.get_doc(
            {
                "doctype": "Property Setter",
                "doc_type": doctype,
                "doctype_or_field": "DocField",
                "field_name": field,
                "property": "in_standard_filter",
                "value": "1",
                "property_type": "Check",
            }
        )
        doc.flags.ignore_permissions = True
        doc.insert(ignore_permissions=True)
        print(f"✓ Company.{field} → in_standard_filter = 1")
    else:
        frappe.db.set_value(
            "Property Setter",
            {"doc_type": doctype, "field_name": field, "property": "in_standard_filter"},
            "value",
            "1",
            update_modified=False,
        )
        print(f"= Company.{field} 的 in_standard_filter 已是 1")

    frappe.db.commit()

    # 3. 验证
    meta = frappe.get_meta(doctype)
    for f in meta.fields:
        if f.fieldname == field:
            print(f"✓ 验证: in_list_view={f.in_list_view} "
                  f"in_standard_filter={f.in_standard_filter} "
                  f"read_only={f.read_only}")
            break

    frappe.clear_cache()
    print("✓ 完成")


if __name__ == "__main__":
    execute()
