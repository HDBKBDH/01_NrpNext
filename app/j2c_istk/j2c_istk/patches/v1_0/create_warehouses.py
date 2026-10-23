"""重建仓库体系

v16 的 Warehouse.name 由 warehouse_name + company 自动组成（"名称 - 公司"），
所以存在性检查必须用 warehouse_name 字段，不能用 name。

Company 拆分（用户确认）：每个仓库群组一个独立 Company。
仓库名暂不改（都是占位名，等真实名称确定后再改）。

  CSRH（大陆主体）      所有仓库 - CSRH
      └ BJ-CSRH            北京销售仓

  SY                    所有仓库 - SY
      └ BJ-SY              北京公司留用（自用）

  HK（香港）            所有仓库 - HK
      └ HK-01/02/03        香港中转仓

  SZ（深圳）            所有仓库 - SZ
      └ SZ-01              深圳中转仓

  GF（闲鱼）            所有仓库 - GF
      └ GF01               虚拟销售渠道（库存恒为 0）

  TT（抖音）            所有仓库 - TT
      └ TT01               虚拟销售渠道（库存恒为 0）

  ISOTENKAI（日本）      所有仓库
      ├ JP                  日本物流仓
      └ JP-LOCAL            日本公司留用（自用）

币种全部 CNY（记账统一，汇率换算）。
"""

import frappe

CSRH = "CSRH"
SY = "SY"
HK = "HK"
SZ = "SZ"
GF = "GF"
TT = "TT"
ISO = "ISOTENKAI"

TREE = [
    # (warehouse_name, parent_name, company, type, country, selfuse, virtual, state)
    ("BJ-CSRH", "所有仓库 - CSRH", CSRH, "销售仓", "China", 0, 0, "Sellable"),
    ("BJ-SY", "所有仓库 - SY", SY, "自用仓", "China", 1, 0, "SelfUse"),
    ("HK-01", "所有仓库 - HK", HK, "中转仓", "Hong Kong", 0, 0, "InTransit"),
    ("HK-02", "所有仓库 - HK", HK, "中转仓", "Hong Kong", 0, 0, "InTransit"),
    ("HK-03", "所有仓库 - HK", HK, "中转仓", "Hong Kong", 0, 0, "InTransit"),
    ("SZ-01", "所有仓库 - SZ", SZ, "中转仓", "China", 0, 0, "InTransit"),
    ("GF01", "所有仓库 - GF", GF, "虚拟仓", "China", 0, 1, "Sellable"),
    ("TT01", "所有仓库 - TT", TT, "虚拟仓", "China", 0, 1, "Sellable"),
    ("JP", "所有仓库", ISO, "物流仓", "Japan", 0, 0, "InTransit"),
    ("JP-LOCAL", "所有仓库", ISO, "自用仓", "Japan", 1, 0, "SelfUse"),
]

ROOTS = [
    ("所有仓库 - CSRH", CSRH),
    ("所有仓库 - SY", SY),
    ("所有仓库 - HK", HK),
    ("所有仓库 - SZ", SZ),
    ("所有仓库 - GF", GF),
    ("所有仓库 - TT", TT),
    ("所有仓库", ISO),
]


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

    # 3. 设置每个 Company 的默认收货仓
    #
    # ERPNext 建 Company 时会建一个 warehouse_name='仓库' 的默认收货仓
    # 并写进 Company.default_warehouse。我们用自己的实体仓代替它。
    # （仓库「仓库」本身在 split_companies 里会被删掉）
    DEFAULT_WAREHOUSE = {
        CSRH: "BJ-CSRH",
        SY: "BJ-SY",
        HK: "HK-01",
        SZ: "SZ-01",
        GF: "GF01",
        TT: "TT01",
        ISO: "JP",
    }
    for company, wh_name in DEFAULT_WAREHOUSE.items():
        if not frappe.db.exists("Company", company):
            continue
        actual = frappe.db.get_value(
            "Warehouse", {"warehouse_name": wh_name, "company": company}, "name"
        )
        if not actual:
            print(f"  ! {company}: 找不到 {wh_name}，跳过默认仓设置")
            continue
        cur = frappe.db.get_value("Company", company, "default_warehouse")
        if cur != actual:
            frappe.db.set_value("Company", company, "default_warehouse", actual)
            print(f"  ✓ {company}.default_warehouse = {actual}")