import frappe
from frappe.model.document import Document


class CustomsDeclaration(Document):
    def validate(self):
        self.set_model_names()
        self.calculate_declared_values()

    def set_model_names(self):
        for row in self.items:
            if row.item:
                row.model_name = frappe.db.get_value(
                    "Item", row.item, "item_name"
                )

    def calculate_declared_values(self):
        total = 0
        count = 0
        for row in self.items:
            row.declared_amount = round(
                frappe.utils.flt(row.declared_price)
                * frappe.utils.flt(row.quantity or 1),
                2,
            )
            total += row.declared_amount
            count += frappe.utils.flt(row.quantity or 1)

        self.declared_value = round(total, 2)
        self.item_count = count

    def on_submit(self):
        self.auto_collect_images()

    def auto_collect_images(self):
        """从拆解单零件行自动带出商品图片（报关复用拆解图）"""
        serials = [r.serial_number for r in self.items if r.serial_number]
        if not serials:
            return

        img_map = frappe.get_all(
            "Disassembly Note Item",
            filters={"serial_number": ("in", serials)},
            fields=["serial_number", "images"],
        )
        img_map = {r["serial_number"]: r["images"] for r in img_map if r["images"]}

        for row in self.items:
            if not row.image and row.serial_number in img_map:
                row.image = img_map[row.serial_number]

        self.db_update()
