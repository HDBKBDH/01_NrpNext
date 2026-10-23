"""重建仓库体系

v16的 Warehouse.name 由 warehouse_name + company 自动组成（"名称 - 公司"），
所以存在性检查必须用 warehouse_name 字段，不能用 name。

CSRH 公司（大陆）：
    所有仓库 - CSRH
           ├ HK-01/02/03 香港中转仓
      ├ SZ-01       深圳中转仓
      ├ BJ-CSRH     北京销售仓
      ├ BJ-SY       北京公司留用（自用）
      └ GOOFISH / TIKTOK  虚拟销售渠道（库存恒为 0）

ISOTENKAI 公司（日本）：
    所有仓库 - ISTK
      ├ JP              日本物流仓
      └ JP-LOCAL        日本公司留用（自用）
"""

import frappe

CSRH = "CSRH"
ISO = "ISOTENKAI"

TREE = [
    # (warehouse_name, parent_name, company, type, country, selfuse, virtual, state)
    ("HK-01", "所有仓库 - CSRH", CSRH, "中转仓", "Hong Kong", 0, 0, "InTransit"),
    ("HK-02", "所有仓库 - CSRH", CSRH, "中转仓", "Hong Kong", 0, 0, "InTransit"),
    ("HK-03", "所有仓库 - CSRH", CSRH, "中转仓", "Hong Kong", 0, 0, "InTransit"),
    ("SZ-01", "所有仓库 - CSRH", CSRH, "中转仓", "China", 0, 0, "InTransit"),
    ("BJ-CSRH", "所有仓库 - CSRH", CSRH, "销售仓", "China", 0, 0, "Sellable"),
    ("BJ-SY", "所有仓库 - CSRH", CSRH, "自用仓", "China", 1, 0, "SelfUse"),
    ("GOOFISH", "所有仓库 - CSRH", CSRH, "虚拟仓", "China", 0, 1, "Sellable"),
    ("TIKTOK", "所有仓库 - CSRH", CSRH, "虚拟仓", "China", 0, 1, "Sellable"),
    ("JP", "所有仓库 - ISTK", ISO, "物流仓", "Japan", 0, 0, "InTransit"),
    ("JP-LOCAL", "所有仓库 - ISTK", ISO, "自用仓", "Japan", 1, 0, "SelfUse"),
]

ROOTS = [("所有仓库 - CSRH", CSRH), ("所有仓库 - ISTK", ISO)]


def _exists(warehouse_name, company):
    """按 warehouse_name + company 判断是否存在（v16 的 name 带公司后缀）"""
    return bool(
        frappe.db.exists(
            "Warehouse", {"warehouse_name": warehouse_name, "company": company}
        )
    )


def _upsert(values):
    """存在则更新字段，不存在则新建"""
    warehouse_name = values["warehouse_name"]
    company = values["company"]

    if _exists(warehouse_name, company):
        wh_name = frappe.db.get_value(
            "Warehouse", {"warehouse_name": warehouse_name, "company": company}, "name"
        )
        frappe.db.set_value("Warehouse", wh_name, values, update_modified=False)
        return "updated"

    frappe.get_doc(dict(doctype="Warehouse", **values)).insert(
        ignore_permissions=True
    )
    return "created"


def execute():
    # 1. 根仓库
    for root_name, company in ROOTS:
        if not frappe.db.exists("Company", company):
            print(f"  x Company {company} 不存在，跳过")
            continue
        if not frappe.db.exists("Warehouse", root_name):
            frappe.get_doc(
                {
                    "doctype": "Warehouse",
                    "warehouse_name": root_name,
                    "company": company,
                    "is_group": 1,
                }
            ).insert(ignore_permissions=True)
            print(f"  + 根仓库 {root_name}")

    # 2. 业务仓库（幂等 upsert）
    created = updated = skipped = 0
    for name, parent, company, wtype, country, selfuse, virtual, state in TREE:
        if not frappe.db.exists("Company", company):
            skipped += 1
            continue

        action = _upsert(
            {
                "warehouse_name": name,
                "parent_warehouse": parent,
                "company": company,
                "st_warehouse_type": wtype,
                "st_country": country,
                "st_is_selfuse": selfuse,
                "st_is_virtual": virtual,
                "st_stock_state": state,
            }
        )
        if action == "created":
            created += 1
            print(f"  + {name} ({company})")
        else:
            updated += 1

    frappe.db.commit()
    print(f"  仓库: 新建 {created}，更新 {updated}，跳过 {skipped}")