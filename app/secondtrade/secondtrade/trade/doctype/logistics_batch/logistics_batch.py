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
    "LocalDisposal": "境内处置收入",
}

# 不参与成本分摊的处置方式（日本境内处理）
LOCAL_DISPOSITIONS = {"PartsOnly", "Scrap"}


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
        """计算批次费用

        境内处置收入（LocalDisposal）是回收款，会冲减可分摊总额：
          支出合计 = Σ(非LocalDisposal)
          处置收入 = Σ(LocalDisposal)
          可分摊总额 = 支出合计 - 处置收入
        """
        expense = 0.0
        disposal = 0.0

        for row in self.costs:
            amt = frappe.utils.flt(row.amount_cny)
            if row.cost_category == "LocalDisposal":
                disposal += amt
            else:
                expense += amt

        self.local_disposal_income = round(disposal, 2)
        self.total_cost = round(expense, 2)
        self.allocatable_cost = round(expense - disposal, 2)

    # ---------------- 分摊 ----------------

    def build_allocations(self):
        """收集批次内所有出口件，按参考价权重分摊批次可分摊成本

        境内处理件（PartsOnly / Scrap）不参与分摊
        """
        self.allocated = []
        if not self.allocatable_cost:
            return

        rows = frappe.get_all(
            "Disassembly Note Item",
            filters={
                "parent": ("in", [s.disassembly_note for s in self.source_disassemblies]),
                "docstatus": 1,
                "disposition": ("not in", list(LOCAL_DISPOSITIONS)),
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

        # 注意：self.allocated 是 Child Table（Allocation Detail）。
        # 必须 append Document 对象，不能 append裸 dict——
        # 裸dict 会让 Frappe 的 global_search/update_global_search
        # 访问 d.parent 时抛 AttributeError: 'dict' object has no attribute 'parent'
        def _append_row(r, ratio, cost):
            row = frappe.get_doc(
                {
                    "doctype": "Cost Allocation",
                    "serial_number": r["serial_number"],
                    "item": r["item"],
                    "component_type": r["component_type"],
                    "weight_ratio": round(ratio, 6),
                    "allocated_cost": round(cost, 2),
                }
            )
            row.flags.ignore_permissions = True
            row.flags.ignore_mandatory = True
            self.allocated.append(row)

        if total_ref <= 0:
            # 参考价全为 0 时按件数均摊
            per_item = self.allocatable_cost / len(rows)
            for r in rows:
                _append_row(r, 0, per_item)
            return

        for r in rows:
            sn = r["serial_number"]
            ratio = weight_map[sn] / total_ref
            _append_row(r, ratio, self.allocatable_cost * ratio)

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

        name_map = {r["name"]: r for r in dn_items}
        for a in self.allocated:
            sn = a.serial_number
            cost = a.allocated_cost

            target = next(
                (v for k, v in name_map.items() if v["serial_number"] == sn),
                None,
            )
            if not target:
                continue

            doc = frappe.get_doc("Disassembly Note Item", target["name"])
            doc.allocated_logistics_cost = cost
            doc.final_cost = calculate_final_cost(doc)
            # 子表行：跳过 update_after_submit 校验
            #（ignore_validate_update 不是 save() 的合法参数，会 TypeError）
            doc.flags.ignore_permissions = True
            doc.flags.ignore_validate_update = True
            doc.save(ignore_permissions=True)
