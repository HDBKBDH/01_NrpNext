"""创建型号主数据（Item）

数据来源：2026-10-22 采购目录（旧进存销软件导出）+ 设计补充
item_group 用 v16 完整name（多级路径形如"DDR4"）
"""

import frappe

# UOM（单位）
UOMS = ["个", "对", "台", "只", "条", "张"]

# Brand（品牌，从 MODELS 提取）



MODELS = [
    ("CR-VEN-3200-32G", "Corsair VENGERNCE DDR4-3200 32G(16G*2)", "DDR4", "Corsair", "VENGERNCE", "DDR4-3200", "32G(16G*2)", "3200"),
    ("CR-VEN-2666-32G", "Corsair VENGERNCE DDR4-2666 32G(16G*2)", "DDR4", "Corsair", "VENGERNCE", "DDR4-2666", "32G(16G*2)", "2666"),
    ("GS-SNX-3200-16G", "G.Skill SniperX DDR4-3200 16G(8G*2)", "DDR4", "G.Skill", "SniperX", "DDR4-3200", "16G(8G*2)", "3200"),
    ("SKH-ECC-3200-32G", "SK hynix DDR4-ECC-3200 32G", "DDR4", "SK hynix", "ECC", "DDR4-3200-ECC", "32G", "3200"),
    ("SAM-ECC-3200-32G", "SAMSUNG DDR4-ECC-3200 32G", "DDR4", "SAMSUNG", "ECC", "DDR4-3200-ECC", "32G", "3200"),
    ("CR-VEN-5600-32G", "Corsair VENGERNCE DDR5-5600 32G(16G*2)", "DDR5", "Corsair", "VENGERNCE", "DDR5-5600", "32G(16G*2)", "5600"),
    ("KS-FURY-6000-32G", "KINGSTON FURY BEAST DDR5-6000 32G(16G*2)", "DDR5", "KINGSTON", "FURY BEAST", "DDR5-6000", "32G(16G*2)", "6000"),
    ("CRU-PRO-5600-32G", "Crucial DDR5 PRO-5600 32G", "DDR5", "Crucial", "PRO", "DDR5-5600", "32G", "5600"),
    ("INT-I7-14700F", "Intel Core i7-14700F", "CPU", "Intel", "Core", "i7-14700F", "", ""),
    ("INT-I7-13700F", "Intel Core i7-13700F", "CPU", "Intel", "Core", "i7-13700F", "", ""),
    ("INT-I5-13700F", "Intel Core i5-13700F", "CPU", "Intel", "Core", "i5-13700F", "", ""),
    ("AMD-R5-3700X", "AMD Ryzen 5 3700X", "CPU", "AMD", "Ryzen", "R5-3700X", "", ""),
    ("AMD-R5-5700X", "AMD Ryzen 5 5700X", "CPU", "AMD", "Ryzen", "R5-5700X", "", ""),
    ("ASUS-TUF-4070", "ASUS TUF RTX4070 O12G", "显卡", "ASUS", "TUF", "RTX4070", "12G", ""),
    ("ASUS-ROG-3090", "ASUS ROG STRIX RTX3090 OC 24GB", "显卡", "ASUS", "ROG STRIX", "RTX3090-OC", "24G", ""),
    ("MSI-4070S", "MSI RTX4070 SUPER", "显卡", "MSI", "GAMING", "RTX4070-S", "12G", ""),
    ("MSI-5060TI", "MSI RTX5060TI", "显卡", "MSI", "GAMING", "RTX5060TI", "8G", ""),
    ("ZOT-3080TI", "ZOTAC RTX3080TI", "显卡", "ZOTAC", "AMP", "RTX3080TI", "12G", ""),
    ("GLK-4070", "GALAKURO RTX4070", "显卡", "GALAKURO", "", "RTX4070", "12G", ""),
    ("PAL-5060", "Palit RTX5060", "显卡", "Palit", "", "RTX5060", "8G", ""),
    ("INO-5070", "INNO3D RTX5070", "显卡", "INNO3D", "", "RTX5070", "12G", ""),
    ("ASR-B760M", "ASROCK B760M", "主板", "ASROCK", "B760", "B760M", "", ""),
    ("MSI-B760MM", "MSI MAG B760M MORTAR WIFI", "主板", "MSI", "MAG", "B760M-MORTAR", "", ""),
    ("ASR-B550M", "ASROCK B550M", "主板", "ASROCK", "B550", "B550M", "", ""),
    ("MU-MTFD-1T", "MICRON 2400 MTFDKBA1T0QFM 1.0TB", "存储", "MICRON", "2400", "MTFDKBA1T0QFM", "1TB", ""),
    ("SAM-870EVO-1T", "SAMSUNG 870 EVO 1TB", "存储", "SAMSUNG", "870 EVO", "870-EVO", "1TB", ""),
    ("SAM-980P-1T", "SAMSUNG 980 PRO 1TB", "存储", "SAMSUNG", "980 PRO", "980-PRO", "1TB", ""),
    ("WD-SN850X-2T", "WD_BLACK SN850X 2TB", "存储", "WD", "SN850X", "SN850X", "2TB", ""),
]


def ensure_uoms():
    """创建缺失的 UOM（单位）"""
    made = 0
    for u in UOMS:
        if frappe.db.exists("UOM", u):
            continue
        frappe.get_doc({"doctype": "UOM", "uom_name": u}).insert(ignore_permissions=True)
        made += 1
    frappe.db.commit()
    print(f"  + UOM: 新建 {made}")
    return made


def ensure_brands():
    """创建缺失的 Brand（品牌）"""
    made = 0
    for b in sorted({m[3] for m in MODELS}):
        if frappe.db.exists("Brand", b):
            continue
        frappe.get_doc({"doctype": "Brand", "brand": b}).insert(ignore_permissions=True)
        made += 1
    frappe.db.commit()
    print(f"  + Brand: 新建 {made}")
    return made


def execute():
    ensure_uoms()
    ensure_brands()

    created = skipped = 0
    for code, name, group, brand, series, model, cap, freq in MODELS:
        if frappe.db.exists("Item", code):
            skipped += 1
            continue

        # 品类必须存在
        if not frappe.db.exists("Item Group", group):
            print(f"  x 品类不存在: {group}（跳过 {code}）")
            continue

        frappe.get_doc({
            "doctype": "Item",
            "item_code": code,
            "item_name": name,
            "item_group": group,
            "brand": brand,
            "is_stock_item": 1,
            "is_sales_item": 1,
            "is_purchase_item": 0,   # 整机采购，零件不直接采购
            "is_second_hand": 1,
            "condition_grade": "Good",
            "stock_category": "InTransit",
            "model_series": series,
            "model_number": model,
            "capacity": cap,
            "frequency": freq,
            "stock_uom": "个",
        }).insert(ignore_permissions=True)
        created += 1
        print(f"  + {code:20s} {name}")

    frappe.db.commit()
    print(f"\n  型号: 新建 {created}，跳过 {skipped}，共 {len(MODELS)}")


if __name__ == "__main__":
    frappe.init(site="erp.motitoo.com")
    frappe.connect()
    execute()
