import frappe
from frappe import _
from frappe.model.document import Document

from secondtrade.utils.cost_allocation import (
    allocate_by_reference_price,
    calculate_final_cost,
)
from secondtrade.utils.label_generator import generate_serial_number


class DisassemblyNote(Document):
    def validate(self):
        self.validate_duplicate_serials()
        self.calculate_totals()
        self.calculate_allocations()

    def on_submit(self):
        self.create_serial_numbers()

    # ---------------- 校验 ----------------

    def validate_duplicate_serials(self):
        """同一拆解单内SN 不可重复"""
        if not self.items:
            return

        serials = [r.serial_number for r in self.items if r.serial_number]
        dupes = {s for s in serials if serials.count(s) > 1}
        if dupes:
            frappe.throw(
                _("序列号重复：{0}").format(", ".join(sorted(dupes))),
                title=_("重复序列号"),
            )

    # ---------------- 计算 ----------------

    def calculate_totals(self):
        self.total_reference_price = sum(
            frappe.utils.flt(r.market_ref_price_cny) for r in self.items
        )
        self.total_allocated_cost = sum(
            frappe.utils.flt(r.allocated_purchase_cost) for r in self.items
        )

    def calculate_allocations(self):
        """按采购时参考价权重分摊整机成本到零件"""
        if not self.items or not self.cny_cost:
            return

        # 已提交后不再重算（成本锁定）
        if self.docstatus == 1:
            return

        for row in self.items:
            row.final_cost = calculate_final_cost(row)

        # 参考价合计为 0 时按数量均摊
        if self.total_reference_price <= 0:
            per_item = frappe.utils.flt(self.cny_cost) / len(self.items)
            for row in self.items:
                row.allocated_purchase_cost = round(per_item, 2)
            frappe.msgprint(
                _("参考价为 0，已按件数均摊采购成本"),
                indicator="orange",
            )
            return

        allocate_by_reference_price(
            [
                {
                    "market_ref_price_cny": r.market_ref_price_cny,
                    "_target": _AllocTarget(r, "allocated_purchase_cost"),
                }
                for r in self.items
            ],
            self.cny_cost,
        )

        for row in self.items:
            row.final_cost = calculate_final_cost(row)

    # ---------------- SN 生成 ----------------

    def create_serial_numbers(self):
        """提交时生成 Serial Number 主数据"""
        created = []

        for row in self.items:
            if not row.serial_number:
                sn = generate_serial_number(
                    self.dn_name, row.component_type, row.sequence_no
                )
                row.serial_number = sn
                created.append(sn)

            if not frappe.db.exists("Serial Number", row.serial_number):
                self._make_serial_number(row)

        self.db_update()

    def _make_serial_number(self, row):
        sn = frappe.get_doc(
            {
                "doctype": "Serial Number",
                "name": row.serial_number,
                "item_code": row.item,
                "company": self.company,
                "warehouse": self.warehouse,
                "status": "Active",
            }
        )
        sn.flags.ignore_permissions = True
        sn.flags.ignore_mandatory = True
        sn.insert(ignore_mandatory=True)


class _AllocTarget:
    """轻量适配器：让分摊函数能写入 Child DocType 字段"""

    def __init__(self, doc, attr):
        self._doc = doc
        self._attr = attr

    def __setattr__(self, key, value):
        if key == "allocated_cost":
            setattr(self._doc, self._attr, value)
        else:
            object.__setattr__(self, key, value)
