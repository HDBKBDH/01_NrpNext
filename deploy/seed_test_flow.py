"""造测试数据：采购 → 拆解 → 物流批次 → 验证成本分摊

场景照搬旧数据 20261003002 MOUSE G-TUNE DG-I7G7A：
  日元原价 217,811 · 汇率 0.043 · 实际 CNY 成本 9,365.87
  拆出：CPU / MEM×2 / GPU / MB / NVME（出口销售）
        PSU / CHS（日本境内处理，拍卖回收）

物流批次：
  日本境内运费 59 CNY · 仓储操作 86 CNY · 头程货运 680 CNY
  清关税费 42 CNY · 境内处置收入 +120 CNY（PSU 80 + CHS 40）
  → 可分摊 = (59+86+680+42) - 120 = 747 CNY
"""

import frappe

# ---------- 测试参数 ----------
PURCHASE = {
    "jpy": 217811,
    "rate": 0.043,
    "date": "2026-10-03",
    "tax_refund": "PendingProof",
    "payment": "JapanPostBank",
    "seller_type": "Company",
    "platform": "ReRe",
    "local_shipping_jpy": 1220,
}

# (component_type, item_code, seq_start, qty, ref_price, disposition)
#内存套装：2 个 SN（MEM-01 / MEM-02），但参考价按整套算
PARTS = [
    ("CPU",  "INT-I7-14700F",   1, 1, 2400, "Normal"),
    ("MEM",  "CR-VEN-5600-32G", 1, 2, 4200, "Normal"),
    ("GPU",  "ASUS-TUF-4070",   1, 1, 5200, "Normal"),
    ("MB",   "ASR-B760M",       1, 1,  800, "Normal"),
    ("NVME", "SAM-980P-1T",     1, 1,  900, "Normal"),
]

LOCAL_PARTS = [
    ("PSU", "PartsOnly", 150, "750W 电源"),
    ("CHS", "PartsOnly", 100, "机箱"),
]

# 物流费用（CNY）
FREIGHT = [
    ("LocalShipping", 59.0,  "日本境内运费（1220 JPY）"),
    ("LocalStorage",  86.0,  "仓储+拆解操作"),
    ("ExportFreight", 680.0, "头程货运 日本→香港"),
    ("CustomsDuty",   42.0,  "清关税费"),
    ("LocalDisposal", 120.0, "境内处置收入（PSU 80 + CHS 40）"),
]

DN_NAME = "261003-01"
COMPANY = "ISOTENKAI"
WH = "JP-ISTK - ISTK"


def banner(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def main():
    frappe.init(site="erp.motitoo.com")
    frappe.connect()
    frappe.flags.in_test = True

    banner("【1】清理旧测试数据")
    # 物流批次（先于拆解单，因为它引用拆解单）
    for lb in frappe.get_all("Logistics Batch", filters={"batch_date": "2026-10-08"}, pluck="name"):
        doc = frappe.get_doc("Logistics Batch", lb)
        if doc.docstatus == 1:
            doc.cancel()
        frappe.delete_doc("Logistics Batch", lb, force=True, ignore_permissions=True)
        print(f"  x 删除物流批次 {lb}")

    # 拆解单：已提交的必须先 cancel 才能 delete
    for dn in frappe.get_all("Disassembly Note", filters={"name": ["like", "261003-%"]}, pluck="name"):
        doc = frappe.get_doc("Disassembly Note", dn)
        if doc.docstatus == 1:
            doc.cancel()
        frappe.delete_doc("Disassembly Note", dn, force=True, ignore_permissions=True)
        print(f"  x 删除拆解单 {dn}")

    # 最后删 Serial No（v16：主键字段是 serial_no，不是 name）
    for sn in frappe.get_all(
        "Serial No", filters={"serial_no": ["like", "261003-%"]},
        pluck="serial_no",
    ):
        frappe.db.delete("Serial No", {"serial_no": sn})
        print(f"  x 删除 Serial No {sn}")

    frappe.db.commit()

    banner("【2】检查 Item 型号")
    missing = []
    for ctype, code, seq, qty, ref, dispo in PARTS:
        if not frappe.db.exists("Item", code):
            missing.append(code)
    if missing:
        print(f"  x 缺少型号: {missing}")
        return
    print(f"  ✓ 出口件型号 {len(PARTS)} 类齐备")

    banner("【3】创建拆解单（成本分摊）")
    cny = round(PURCHASE["jpy"] * PURCHASE["rate"], 2)
    print(f"  日元原价     {PURCHASE['jpy']:,} JPY")
    print(f"  结算汇率     {PURCHASE['rate']}")
    print(f"  实际 CNY 成本 {cny:>10,.2f}")

    dn = frappe.get_doc({
        "doctype": "Disassembly Note",
        "disassembly_date": PURCHASE["date"],
        "company": COMPANY,
        "warehouse": WH,
        "purpose": "Sale",
        "jpy_original": PURCHASE["jpy"],
        "settlement_rate": PURCHASE["rate"],
        "cny_cost": cny,
        "tax_refund_status": PURCHASE["tax_refund"],
        "payment_method": PURCHASE["payment"],
        "supplier_type": PURCHASE["seller_type"],
        "purchase_platform": PURCHASE["platform"],
        "local_shipping_jpy": PURCHASE["local_shipping_jpy"],
        "items": [],
    })

    # 出口件
    for ctype, code, seq_start, qty, ref, dispo in PARTS:
        for i in range(qty):
            dn.append("items", {
                "item": code,
                "component_type": ctype,
                "sequence_no": seq_start + i,
                "quantity": 1,
                "condition_grade": "Good",
                "disposition": dispo,
                "market_ref_price_cny": ref,
            })

    # 境内件（PSU / CHS）—— 需要 Item，先建占位 Item
    for ctype, dispo, ref, desc in LOCAL_PARTS:
        code = f"GEN-{ctype}-GENERIC"
        if not frappe.db.exists("Item", code):
            frappe.get_doc({
                "doctype": "Item",
                "item_code": code,
                "item_name": f"通用{ctype}（日本境内处理）",
                "item_group": "电源" if ctype == "PSU" else "机箱",
                "is_stock_item": 1,
                "is_sales_item": 0,
                "is_second_hand": 1,
                "stock_uom": "个",
            }).insert(ignore_permissions=True)
            print(f"  + 新建占位Item {code}")

        dn.append("items", {
            "item": code,
            "component_type": ctype,
            "sequence_no": 1,
            "quantity": 1,
            "condition_grade": "Fair",
            "disposition": dispo,
            "market_ref_price_cny": ref,
            "defect_note": desc,
        })

    dn.insert(ignore_permissions=True)
    dn.submit()
    # submit 时才生成 SN，重新加载以读取
    dn = frappe.get_doc("Disassembly Note", dn.name)
    assert dn.name == DN_NAME, f"拆解单号应为 {DN_NAME}，实际 {dn.name}"

    print(f"\n  拆解单: {dn.name}")
    print(f"  {'类型':<6}{'型号':<26}{'SN':<22}{'参考价':>9}{'分摊成本':>11}")
    print("  " + "-" * 74)
    for r in dn.items:
        sn = r.serial_number or "(未生成)"
        print(f"  {r.component_type:<6}{r.item:<26}{sn:<22}{r.market_ref_price_cny:>9,}{r.allocated_purchase_cost:>11,.2f}")
    print("  " + "-" * 74)
    print(f"  {'参考价合计':<54}{dn.total_reference_price:>9,.0f}")
    print(f"  {'已分摊成本':<54}{dn.total_allocated_cost:>11,.2f}")

    # 校验
    export_sum = sum(
        r.allocated_purchase_cost for r in dn.items
        if r.disposition not in ("PartsOnly", "Scrap")
    )
    local_sum = sum(
        r.allocated_purchase_cost for r in dn.items
        if r.disposition in ("PartsOnly", "Scrap")
    )
    print(f"\n  出口件分摊合计  {export_sum:>10,.2f}   (应 = {cny:,.2f})")
    print(f"  境内件分摊合计  {local_sum:>10,.2f}   (应 = 0.00)")
    ok = abs(export_sum - cny) < 0.01 and local_sum == 0
    print(f"  {'✓ 分摊校验通过' if ok else '✗ 分摊异常'}")

    # 关键：先 commit 拆解单，这样后续物流批次失败不会回滚已验证的分摊数据
    frappe.db.commit()

    banner("【4】创建物流批次（含境内处置收入冲减）")
    lb = frappe.get_doc({
        "doctype": "Logistics Batch",
        "batch_date": "2026-10-08",
        "coverage_start": "2026-10-03",
        "coverage_end": "2026-10-03",
        "source_disassemblies": [{"disassembly_note": dn.name}],
        "costs": [
            {"sequence": i + 1, "cost_category": cat,
             "amount_cny": amt, "remark": note}
            for i, (cat, amt, note) in enumerate(FREIGHT)
        ],
    })
    lb.insert(ignore_permissions=True)
    lb.submit()

    print(f"  批次: {lb.name}")
    print(f"  支出合计      {lb.total_cost:>10,.2f}")
    print(f"  境内处置收入  {lb.local_disposal_income:>10,.2f}")
    print(f"  可分摊总额    {lb.allocatable_cost:>10,.2f}")
    print(f"\n  {'SN':<24}{'权重':>10}{'分摊物流成本':>14}")
    print("  " + "-" * 48)
    for a in lb.allocated:
        print(f"  {a.serial_number:<24}{a.weight_ratio:>10.4f}{a.allocated_cost:>14,.2f}")
    print("  " + "-" * 48)
    print(f"  {'合计':<34}{sum(a.allocated_cost for a in lb.allocated):>14,.2f}")

    banner("【5】最终成本汇总")
    rows = frappe.db.sql("""
        SELECT
            dni.serial_number,
            dni.component_type,
            dni.item,
            dni.disposition,
            dni.market_ref_price_cny   AS ref_price,
            dni.allocated_purchase_cost AS purchase_cost,
            dni.allocated_logistics_cost AS logistics_cost,
            dni.final_cost             AS final_cost
        FROM `tabDisassembly Note Item` dni
        WHERE dni.parent = %s
        ORDER BY dni.component_type, dni.sequence_no
    """, dn.name, as_dict=True)

    print(f"  {'类型':<6}{'SN':<22}{'参考价':>9}{'采购分摊':>11}{'物流分摊':>11}{'最终成本':>11}")
    print("  " + "-" * 70)
    tot_ref = tot_pur = tot_log = tot_fin = 0
    for r in rows:
        mark = "*" if r.disposition in ("PartsOnly", "Scrap") else " "
        print(f" {mark}{r.component_type:<5}{(r.serial_number or '(境内处理)'):<22}"
              f"{r.ref_price:>9,}{r.purchase_cost:>11,.2f}"
              f"{r.logistics_cost:>11,.2f}{r.final_cost:>11,.2f}")
        tot_ref += r.ref_price
        tot_pur += r.purchase_cost
        tot_log += r.logistics_cost
        tot_fin += r.final_cost
    print("  " + "-" * 70)
    print(f"  {'合计':<33}{tot_ref:>9,}{tot_pur:>11,.2f}{tot_log:>11,.2f}{tot_fin:>11,.2f}")

    exp_rows = [r for r in rows if r.disposition not in ("PartsOnly", "Scrap")]
    exp_ref = sum(r.ref_price for r in exp_rows)
    exp_fin = sum(r.final_cost for r in exp_rows)
    print(f"\n  * = 日本境内处理（不摊成本）")
    print(f"\n  出口件 {len(exp_rows)} 件:")
    print(f"    合计参考价   {exp_ref:>12,.0f} CNY")
    print(f"    合计最终成本 {exp_fin:>12,.2f} CNY")
    print(f"    采购溢价空间  {(exp_ref - exp_fin) / exp_fin * 100:>11.1f}%")

    banner("完成")
    print(f"  拆解单{dn.name} · 物流批次 {lb.name}")
    print(f"  Serial No 已生成 {len(rows)} 条（不带仓库，靠拆解单追踪）")


if __name__ == "__main__":
    main()