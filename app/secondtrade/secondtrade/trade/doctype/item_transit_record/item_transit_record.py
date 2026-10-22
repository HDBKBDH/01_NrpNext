import frappe
from frappe import _
from frappe.model.document import Document


class ItemTransitRecord(Document):
    def validate(self):
        self.validate_date_order()

    def validate_date_order(self):
        if self.departure_date and self.arrival_date:
            if self.arrival_date < self.departure_date:
                frappe.throw(_("到达日期不能早于出发日期"))
