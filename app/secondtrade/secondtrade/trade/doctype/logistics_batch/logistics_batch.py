import frappe
from frappe import _
from frappe.model.document import Document

from secondtrade.utils.cost_allocation import allocate_by_reference_price

COST_CATEGORY_LABELS = {
    "LocalShipping": "日本境内运输",
    "LocalStorage": "日本境内仓储",
    "ExportFreight": "出境货运",
    "HKTransit": "香港中转",
    "CNTransport": "大陆段运输",
    "CustomsDuty": "关税",
    "CustomsAgent": "清关代理",
    "Insurance": "保险",
    "Refund": "退货返款",
    "Other": "其他",
}


class LogisticsBatch(Document):
    def validate(self):
        self.set_cost_category_names()
        self.calculate_total_cost()

    def on_submit(self):
        self.build_allocations()
        self.write_back_to_disassembly()

    # ---------------- 校验与计算 ----------------

    def set_cost_category_names(self):
        for row in self.costs:
            row.cost_category_name = COST_CATEGORY_LABELS.get(
                row.cost_category, row.cost_category
            )

    def calculate_total_cost(self):
        total = sum(frappe.utils.flt(r.amount_cny) for r in self.costs)
        self.total_cost = round(total, 2)

    # ---------------- 分摊 ----------------

    def build_allocations(self):
        """收集批次内所有零件，按参考价权重分摊批次成本"""
        self.allocated = []
        if not self.total_cost:
            return

        rows = frappe.get_all(
            "Disassembly Note Item",
            filters={
                "parent": ("in", [s.disassembly_note for s in self.source_disassemblies]),
                "docstatus": 1,
            },
            fields=[
                "parent",
                "serial_number",
                "item",
                "component_type",
                "market_ref_price_cny",
            ],
        )

        if not rows:
            return

        weight_map = {r["serial_number"]: frappe.utils.flt(r["market_ref_price_cny"]) for r in rows}
        total_ref = sum(weight_map.values())

        if total_ref <= 0:
            # 参考价全为 0 时按件数均摊
            per_item = self.total_cost / len(rows)
            self.allocated = [
                {
                    "serial_number": r["serial_number"],
                    "item": r["item"],
                    "component_type": r["component_type"],
                    "weight_ratio": 0,
                    "allocated_cost": round(per_item, 2),
                }
                for r in rows
            ]
            return

        for r in rows:
            sn = r["serial_number"]
            ratio = weight_map[sn] / total_ref
            self.allocated.append(
                {
                    "serial_number": sn,
                    "item": r["item"],
                    "component_type": r["component_type"],
                    "weight_ratio": round(ratio, 6),
                    "allocated_cost": round(self.total_cost * ratio, 2),
                }
            )

    def write_back_to_disassembly(self):
        """把物流分摊结果写回拆解单，重算最终成本"""
        from secondtrade.utils.cost_allocation import calculate_final_cost

        if not self.allocated:
            return

        serials = [a.serial_number for a in self.allocated]
        dn_items = frappe.get_all(
            "Disassembly Note Item",
            filters={"serial_number": ("in", serials), "docstatus": 1},
            fields=["name", "serial_number", "allocated_purchase_cost",
                    "allocated_logistics_cost", "tax_refund_adjustment"],
        )
        if not dn_items:
            return

        # 允许提交
        frappe.db.set_value(
            "Disassembly Note Item",
            {"parenttype": "Disassembly Note"},
            None,
        )

        name_map = {r["name"]: r for r in dn_items}
        for a in self.allocated:
            target = next(
                (v for k, v in name_map.items() if v["serial_number"] == a.serial_number),
                None,
            )
            if not target:
                continue

            doc = frappe.get_doc("Disassembly Note Item", target["name"])
            doc.allocated_logistics_cost = a.allocated_cost
            doc.final_cost = calculate_final_cost(doc)
            doc.flags.ignore_permissions = True
            doc.flags.ignore_validate_update = True
            doc.save(ignore_permissions=True, ignore_validate_update=True)
