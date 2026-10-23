# -*- coding: utf-8 -*-
"""入库单 —— 散件 / 整机 / 拆分件统一入口

提交时：生成 ERPNext Item + 标准库存流水（Stock Entry）。
取消时：反向冲销库存流水。
"""
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

UOM_PAIR = "对"          # 「对」需要 2 个商品编号
MAX_SERIAL = 2
DEFAULT_ITEM_GROUP = "J2C_ISTK"
DEFAULT_UOM = "Nos"


class StockIn(Document):
    def validate(self):
        self.validate_category()
        self.validate_serial_count()
        self.calculate_cny()
        self.set_company_from_warehouse()

    def before_submit(self):
        self.create_items()

    def on_submit(self):
        self.create_stock_entry()

    def on_cancel(self):
        self.cancel_stock_entry()

    # ---------- 校验 ----------

    def validate_category(self):
        if self.category not in ("散件", "整机", "拆分件"):
            frappe.throw(_("类别无效：{0}").format(self.category))

    def validate_serial_count(self):
        """单位为「对」需 2 个编号；其他单位只能 1 个。"""
        rows = self.serial_numbers or []
        if not rows:
            frappe.throw(_("至少需要一个商品编号"))

        n = len([r for r in rows if r.serial_no])
        if n == 0:
            frappe.throw(_("至少需要一个商品编号"))

        if n > MAX_SERIAL:
            frappe.throw(_("商品编号最多 {0} 个，当前 {1} 个").format(MAX_SERIAL, n))

        if self.uom == UOM_PAIR and n != 2:
            frappe.throw(_("单位为「对」时需要 2 个商品编号，当前 {0} 个").format(n))

        if self.uom != UOM_PAIR and n != 1:
            frappe.throw(_("单位为「{0}」时只能有 1 个商品编号，当前 {1} 个").format(self.uom, n))

        # 编号不能重复
        codes = [r.serial_no for r in rows if r.serial_no]
        if len(codes) != len(set(codes)):
            frappe.throw(_("商品编号重复"))

    def set_company_from_warehouse(self):
        """Company 由仓库带出。"""
        if not self.warehouse:
            return

        wh_company = frappe.db.get_value("Warehouse", self.warehouse, "company")
        if not wh_company:
            frappe.throw(_("仓库 {0} 未设置公司").format(self.warehouse))

        if not self.company:
            self.company = wh_company
        elif self.company != wh_company:
            frappe.throw(_("仓库 {0} 属于公司 {1}，与当前选择的 {2} 不一致").format(
                self.warehouse, wh_company, self.company))

    # ---------- 金额 ----------

    def calculate_cny(self):
        """CNY = (采购价 + 运费 - 折扣JPY) × 当日汇率"""
        jpy = flt(self.purchase_price_jpy) + flt(self.shipping_jpy) - flt(self.discount)
        self.total_cny = round(jpy * flt(self.exchange_rate), 2)

    # ---------- Item 生成 ----------

    def create_items(self):
        """为每个商品编号创建 ERPNext Item。"""
        group = self.get_or_create_item_group()
        uom = self.get_uom()

        for row in self.serial_numbers or []:
            if not row.serial_no:
                continue

            item_code = row.serial_no.strip()

            if frappe.db.exists("Item", item_code):
                row.item_code = item_code
                continue

            item = frappe.get_doc({
                "doctype": "Item",
                "item_code": item_code,
                "item_name": item_code,
                "item_group": group,
                "stock_uom": uom,
                "is_stock_item": 1,
            })
            if self.manufacturer:
                item.model_number = self.manufacturer
            if self.specification:
                item.model_series = self.specification

            item.flags.ignore_permissions = True
            item.insert(ignore_if_duplicate=True)
            row.item_code = item_code

    def get_or_create_item_group(self):
        if not frappe.db.exists("Item Group", DEFAULT_ITEM_GROUP):
            doc = frappe.get_doc({
                "doctype": "Item Group",
                "item_group_name": DEFAULT_ITEM_GROUP,
                "parent_item_group": "All Item Groups",
                "is_group": 1,
            })
            doc.flags.ignore_permissions = True
            doc.insert(ignore_if_duplicate=True)
        return DEFAULT_ITEM_GROUP

    def get_uom(self):
        if not frappe.db.exists("UOM", DEFAULT_UOM):
            doc = frappe.get_doc({"doctype": "UOM", "uom_name": DEFAULT_UOM})
            doc.flags.ignore_permissions = True
            doc.insert(ignore_if_duplicate=True)
        return DEFAULT_UOM

    # ---------- 标准库存流水 ----------

    def create_stock_entry(self):
        """生成标准 Stock Entry（Material Receipt）。

        CNY 成本按商品编号件数均摊：「对」有 2 行，各摊一半。
        """
        rows = [r for r in (self.serial_numbers or []) if r.item_code]
        if not rows:
            frappe.throw(_("没有可入库的商品编号"))

        per_unit = round(flt(self.total_cny) / len(rows), 2)
        cost_center = self.get_cost_center()

        items = [{
            "item_code": r.item_code,
            "qty": flt(self.qty),
            "warehouse": self.warehouse,
            "basic_rate": per_unit,
            "cost_center": cost_center,
        } for r in rows]

        se = frappe.get_doc({
            "doctype": "Stock Entry",
            "stock_entry_type": "Material Receipt",
            "company": self.company,
            "posting_date": self.stock_date,
            "remarks": _("入库单 {0}（{1}）").format(self.name, self.category),
            "items": items,
        })
        se.flags.ignore_permissions = True
        se.insert()
        se.submit()

        self.db_set("stock_entry_ref", se.name)


@frappe.whitelist()
def get_recent_serials(search_term=None, start=0, page_len=20):
    """商品编号输入框的快捷提示 —— 最近录入过的编号。

    返回按最近使用时间倒序的编号列表，前端作为下拉候选。
    """
    result = frappe.db.sql(
        """
        SELECT si.serial_no AS serial_no,
               si.parent AS stock_in,
               si.parentcreation AS created
        FROM `tabStock In Item` si
        WHERE si.serial_no IS NOT NULL
          AND si.serial_no != ''
          AND (%s IS NULL OR si.serial_no LIKE %s)
        ORDER BY si.parentcreation DESC
        LIMIT %s OFFSET %s
        """,
        (search_term, f"%{search_term}%", page_len, start),
        as_dict=True,
    )
    return result

    def get_cost_center(self):
        cc = frappe.db.get_value("Company", self.company, "cost_center")
        return cc or "Main - {0}".format(self.company)

    def cancel_stock_entry(self):
        if not self.stock_entry_ref:
            return
        se = frappe.get_doc("Stock Entry", self.stock_entry_ref)
        if se.docstatus == 1:
            se.flags.ignore_permissions = True
            se.cancel()