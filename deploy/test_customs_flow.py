"""报关单端到端测试

场景：
  1. 从已有拆解单 261003-01（6 件出口零件）抓取
  2. 创建一个散件采购单（2 件单独买的配件）
  3. 从散件采购单也抓一批
  4. 合并到同一张报关单，验证：
     - 日元申报价正确
     - 人民币记账字段隐藏但有值
     - 源单号正确显示
     - 提交时生成证据包 ZIP
"""

import frappe, zipfile, io, os

frappe.init(site="erp.motitoo.com")
frappe.connect()

def banner(t):
    print("\n" + "=" * 68)
    print(t)
    print("=" * 68)

# ── 清理 ──
banner("【0】清理")
for d in ["Customs Declaration", "Evidence Package", "Loose Part Purchase"]:
    for n in frappe.get_all(d, pluck="name"):
        doc = frappe.get_doc(d, n)
        if doc.docstatus == 1:
            doc.cancel()
        frappe.delete_doc(d, n, force=True, ignore_permissions=True)
        print(f"  x {d} {n}")
for sn in frappe.get_all(
    "Serial No",
    filters={"serial_no": ["like", "CUSTOMS-%"]},
    pluck="serial_no",
):
    frappe.db.delete("Serial No", {"serial_no": sn})
    print(f"  x Serial No {sn}")

# 散件采购单的 SN（LPP-xxx）在删除单据后残留，也要清
for sn in frappe.get_all(
    "Serial No",
    filters={"serial_no": ["like", "LPP-%"]},
    pluck="serial_no",
):
    frappe.db.delete("Serial No", {"serial_no": sn})
    print(f"  x Serial No {sn}")
frappe.db.commit()

# ── 汇率设置 ──
banner("【1】贸易设置")
frappe.db.set_single_value("Trade Settings", "jpy_reference_rate", 0.043)
frappe.db.commit()
print(f"  JPY 参考汇率: {frappe.db.get_single_value('Trade Settings', 'jpy_reference_rate')}")

# ── 散件采购单 ──
banner("【2】创建散件采购单（直接买的配件）")
pe = frappe.get_doc({
    "doctype": "Loose Part Purchase",
    "purchase_date": "2026-10-20",
    "po_no": "YA-2026-1015",
    "exchange_rate": 0.0432,
    "tax_refund_status": "Completed",
    "items": [
        {"item": "ASUS-TUF-4070", "component_type": "GPU", "quantity": 1,
         "condition_grade": "Excellent", "unit_price_jpy": 68000},
        {"item": "SAM-980P-1T", "component_type": "NVME", "quantity": 2,
         "condition_grade": "Good", "unit_price_jpy": 5200},
    ],
})
pe.insert(ignore_permissions=True)
pe.submit()
pe = frappe.get_doc("Loose Part Purchase", pe.name)
print(f"  单号: {pe.name}   PO: {pe.po_no}")
print(f"  总额: {pe.total_jpy:,.0f} JPY  = {pe.total_cny:,.2f} CNY")
for r in pe.items:
    print(f"    {r.component_type:5s} {r.item:18s} SN={r.serial_number:24s} "
          f"{r.unit_price_jpy:>8,.0f} JPY  {r.amount_cny:>9,.2f} CNY")

# ── 报关单 ──
banner("【3】创建报关单（拆件 + 散件统一入口）")
cd = frappe.get_doc({
    "doctype": "Customs Declaration",
    "declaration_date": "2026-10-22",
    "declaration_type": "Freight",
    "port": "成田空港",
    "tax_refund_status": "PendingProof",
})
cd.insert(ignore_permissions=True)
print(f"  单号: {cd.name}")

# 从拆解单抓
r1 = cd.get_parts_from_disassembly("261003-01")
print(f"  从拆解单抓取: 新增 {r1['added']} / 跳过 {r1['skipped']} / 共 {r1['total']}")

# 从散件采购单抓
r2 = cd.get_parts_from_purchase(pe.name)
print(f"  从散件单抓取: 新增 {r2['added']} / 跳过 {r2['skipped']} / 共 {r2['total']}")

cd.save(ignore_permissions=True)
cd = frappe.get_doc("Customs Declaration", cd.name)

# ── 验证 ──
banner("【4】报关明细（只显示日元）")
print(f"  {'源单号':14s} {'来源':10s} {'类型':5s} {'型号':20s} {'SN':24s} {'申报单价':>10s} {'申报金额':>12s}")
print("  " + "-" * 100)
for r in cd.items:
    src = "整机拆件" if r.source_type == "Disassembly" else "散件采购"
    print(f"  {r.source_doc or '-':14s} {src:10s} {r.component_type or '-':5s} "
          f"{r.item:20s} {r.serial_number or '-':24s} "
          f"{r.declared_price_jpy:>10,.0f} {r.declared_amount_jpy:>12,.0f}")

print(f"\n  申报总值: {cd.total_declared_jpy:,.0f} 日元   件数: {cd.item_count}")
cny_total = sum(r.declared_amount_cny for r in cd.items)
print(f"  （内部记账）{cny_total:,.2f} 人民币 — 不显示在报关单上")

# 验证 CNY 字段确实隐藏
m = frappe.get_meta("Customs Item")
hidden = [f.fieldname for f in m.fields
          if f.fieldtype == "Currency" and "CNY" in (f.label or "") and f.hidden]
print(f"\n  隐藏的 CNY 字段: {hidden}")

# ── 提交 + 证据包 ──
banner("【5】提交 + 生成证据包")
cd.submit()
cd = frappe.get_doc("Customs Declaration", cd.name)
print(f"  报关单已提交: {cd.docstatus}")
print(f"  证据包: {cd.evidence_package}")

pkg = frappe.get_doc("Evidence Package", cd.evidence_package)
print(f"  证据包文件: {pkg.package_file}")
print(f"  文件数量: {pkg.file_count}")

# 验证 ZIP 内容
# 注意：v16 的 File 表已删除 file_path 列，改用 doc.get_file()
fname = os.path.basename(pkg.package_file)
content = None
try:
    fdoc = frappe.get_doc("File", {"file_name": fname})
    content = fdoc.get_content()
except Exception as e:
    print(f"  (get_content 失败: {e}，尝试 frappe.get_file)")
    try:
        content = frappe.get_file(fdoc.file_url)
    except Exception as e2:
        content = None
        print(f"  (get_file 也失败: {e2})")

if content:
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        print("\n  ZIP 内容:")
        for n in zf.namelist():
            print(f"    {n}  ({zf.getinfo(n).file_size:,} bytes)")

        csv_data = zf.read("manifest.csv").decode("utf-8-sig")
        print("\n  manifest.csv 前 4 行:")
        for line in csv_data.splitlines()[:4]:
            print(f"    {line[:120]}")

        readme = zf.read("README.txt").decode("utf-8")
        print("\n  README.txt:")
        for line in readme.splitlines():
            print(f"    {line}")
else:
    print("  ✗ 无法读取 ZIP")

frappe.db.commit()
print("\n" + "=" * 68)
print("完成")
print("=" * 68)