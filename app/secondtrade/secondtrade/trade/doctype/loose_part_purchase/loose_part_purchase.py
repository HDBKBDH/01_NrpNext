import frappe
from frappe import _
from frappe.model.document import Document


class LoosePartPurchase(Document):
    """散件采购单

    只记录「直接采购的配件」——不是整机拆件的那些。
    比如单独在 Yahoo 拍卖买的显卡、单独买的内存条。

    报关时不区分来源：用户在报关单上直接从这张单抓零件即可，
    明细行会显示源单号（LPP-00001）便于追溯。

    金额以日元记录（采购实际付的日元），
    人民币按结算汇率换算，仅作内部参考。
    """

    def validate(self):
        self.set_model_names()
        self.calculate_totals()

    def on_submit(self):
        self.generate_serial_numbers()

    # ---------------- 计算 ----------------

    def set_model_names(self):
        for row in self.items:
            if row.item and not row.model_name:
                row.model_name = frappe.db.get_value("Item", row.item, "item_name")

    def calculate_totals(self):
        total_jpy = 0.0
        total_cny = 0.0
        rate = frappe.utils.flt(self.exchange_rate)

        for row in self.items:
            qty = frappe.utils.flt(row.quantity or 1)
            unit_jpy = frappe.utils.flt(row.unit_price_jpy)

            row.amount_jpy = round(unit_jpy * qty, 0)

            # 汇率：优先用行上的，没有就用单头的
            row_rate = frappe.utils.flt(row.exchange_rate) or rate
            row.exchange_rate = row_rate

            row.amount_cny = round(row.amount_jpy * row_rate, 2) if row_rate else 0

            total_jpy += row.amount_jpy
            total_cny += row.amount_cny

        self.total_jpy = round(total_jpy, 0)
        self.total_cny = round(total_cny, 2)

    # ---------------- 提交时 ----------------

    def generate_serial_numbers(self):
        """提交时为每件商品生成 Serial No

        SN 格式：LPP-00001-GPU-01
        注意：报关提交时不会再生成（因为这里已经生成了）。
        """
        from secondtrade.utils.label_generator import generate_serial_number

        seq_by_type = {}

        for row in self.items:
            if row.serial_number:
                continue

            ctype = row.component_type or "PART"
            seq_by_type[ctype] = seq_by_type.get(ctype, 0) + 1
            sn = generate_serial_number(self.name, ctype, seq_by_type[ctype])

            if frappe.db.exists("Serial No", {"serial_no": sn}):
                frappe.throw(_("序列号已存在：{0}").format(sn))

            frappe.get_doc(
                {
                    "doctype": "Serial No",
                    "serial_no": sn,
                    "item_code": row.item,
                    "company": self.company,
                    "status": "Active",
                    "posting_date": self.purchase_date,
                }
            ).insert(ignore_mandatory=True)

            row.serial_number = sn
            frappe.db.set_value(
                "Loose Part Purchase Item",
                row.name,
                "serial_number",
                sn,
                update_modified=False,
            )
