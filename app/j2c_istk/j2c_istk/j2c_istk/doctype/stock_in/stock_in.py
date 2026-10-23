# -*- coding: utf-8 -*-
"""入库单 —— 散件 / 整机统一入口

提交时：生成 ERPNext Item + 标准库存流水（Stock Entry）。
取消时：反向冲销库存流水。

字段布局（2026-10-23 用户确认）：
    Section 1  入库时间 | 购买日期 | 到货时间 | 仓库
    Section 2  商品编号子表（含分类/厂商/型号/规格/数量/单位/价格）+ 产品图片 + 公司
    Section 3  当日汇率
    Section 4  购买参考价 | 行情价
    ...
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
    # ---------- 校验 ----------

    def validate(self):
        self.validate_part_type()
        self.set_company_from_warehouse()
        self.validate_rows()
        self.calculate_cny()

    def validate_part_type(self):
        """零件类型 —— 整单一份，在主表。"""
        if not self.part_type:
            frappe.throw(_("请选择零件类型"))

    def validate_rows(self):
        """子表逐行校验。"""
        rows = [r for r in (self.serial_numbers or []) if r.serial_no]
        if not rows:
            frappe.throw(_("至少需要一个商品编号"))

        if len(rows) > MAX_SERIAL:
            frappe.throw(_("商品编号最多 {0} 个，当前 {1} 个").format(MAX_SERIAL, len(rows)))

        codes = [r.serial_no for r in rows]
        if len(codes) != len(set(codes)):
            frappe.throw(_("编号重复"))

        # 类别（散件/整机/拆解件）逐行校验
        for r in rows:
            if r.category not in ("散件", "整机", "拆解件"):
                frappe.throw(_("第 {0} 行类别无效：{1}").format(
                    r.idx, r.category or "空"))

            if r.category == "拆解件" and not r.parent_item:
                frappe.throw(_("第 {0} 行是拆解件，必须关联父入库单").format(r.idx))

        # 单位「对」→ 2 行；其他 → 1 行（单位在主表，整单一份）
        uom = self.uom or "单个"
        if uom == UOM_PAIR and len(rows) != 2:
            frappe.throw(_("单位为「对」时需要 2 个商品编号，当前 {0} 个").format(len(rows)))
        if uom != UOM_PAIR and len(rows) != 1:
            frappe.throw(_("单位为「{0}」时只能有 1 个商品编号，当前 {1} 个").format(uom, len(rows)))

    def set_company_from_warehouse(self):
        """公司完全由仓库决定（前端已移除该字段，设为 hidden）。

        仓库 → Warehouse.company → 本单 company。
        这是 Stock Entry 生成所必需的，列表页可见便于核对。
        """
        if not self.warehouse:
            frappe.throw(_("请选择仓库"))

        wh_company = frappe.db.get_value("Warehouse", self.warehouse, "company")
        if not wh_company:
            frappe.throw(_("仓库 {0} 未设置公司").format(self.warehouse))

        # 唯一真源：仓库所属公司
        self.company = wh_company

    def calculate_cny(self):
        """每行金额计算（汇率已移入子表，逐行可不同）。

        小计¥(JPY) = 采购价 + 运费 - 折扣
        成本¥(CNY) = 小计¥ × 购买汇率
        盈亏 (CNY) =（行情价 - 成本¥）× 数量
        """
        for row in self.serial_numbers or []:
            jpy = flt(row.purchase_price_jpy) + flt(row.shipping_jpy) - flt(row.discount)
            row.total_jpy = round(jpy, 2)
            row.total_cny = round(jpy * flt(row.exchange_rate), 2)

            if row.market_price_cny:
                unit_profit = flt(row.market_price_cny) - flt(row.total_cny)
                row.profit_cny = round(unit_profit * (flt(row.qty) or 1), 2)

    # ---------- Item 生成 ----------

    def before_submit(self):
        self.create_items()

    def create_items(self):
        """为每个编号创建 ERPNext Item。

        Item Group 按「零件类型」（内存/CPU/显卡…）分，
        这样日后在 Item / 库存 / 仓库里都能按零件类型筛选。
        """
        uom = self.get_uom()

        for row in self.serial_numbers or []:
            if not row.serial_no:
                continue

            item_code = row.serial_no.strip()

            if frappe.db.exists("Item", item_code):
                continue

            item = frappe.get_doc({
                "doctype": "Item",
                "item_code": item_code,
                "item_name": item_code,
                "item_group": self.get_item_group(self.part_type),
                "stock_uom": uom,
                "is_stock_item": 1,
            })
            if row.manufacturer:
                item.model_number = row.manufacturer
            if row.specification:
                item.model_series = row.specification

            item.flags.ignore_permissions = True
            item.insert(ignore_if_duplicate=True)

    def get_item_group(self, part_type):
        """零件类型 → Item Group；空值回落到默认组。"""
        name = (part_type or DEFAULT_ITEM_GROUP).strip()
        return self.get_or_create_item_group(name)

    def get_or_create_item_group(self, name=None):
        name = name or DEFAULT_ITEM_GROUP
        if not frappe.db.exists("Item Group", name):
            doc = frappe.get_doc({
                "doctype": "Item Group",
                "item_group_name": name,
                "parent_item_group": DEFAULT_ITEM_GROUP if name != DEFAULT_ITEM_GROUP
                                      else "All Item Groups",
                "is_group": 1,
            })
            doc.flags.ignore_permissions = True
            doc.insert(ignore_if_duplicate=True)
        return name

    def get_uom(self):
        if not frappe.db.exists("UOM", DEFAULT_UOM):
            doc = frappe.get_doc({"doctype": "UOM", "uom_name": DEFAULT_UOM})
            doc.flags.ignore_permissions = True
            doc.insert(ignore_if_duplicate=True)
        return DEFAULT_UOM

    # ---------- 标准库存流水 ----------

    def on_submit(self):
        self.create_stock_entry()

    def create_stock_entry(self):
        """生成标准 Stock Entry（Material Receipt）。

        成本取每行的采购合计(CNY)。同一商品编号出现多行时合并数量、
        累加成本 —— Stock Entry 一行只能有一个 Item。
        """
        rows = [r for r in (self.serial_numbers or []) if r.serial_no]
        if not rows:
            frappe.throw(_("没有可入库的商品编号"))

        cost_center = self.get_cost_center()

        # 同一编号合并：数量累加，成本累加
        merged = {}
        order = []
        for r in rows:
            code = r.serial_no.strip()
            if code not in merged:
                merged[code] = {
                    "item_code": code,
                    "qty": 0.0,
                    "warehouse": self.warehouse,
                    "basic_rate": 0.0,
                    "cost_center": cost_center,
                }
                order.append(code)
            qty = flt(r.qty) or 1
            m = merged[code]
            m["basic_rate"] += flt(r.total_cny)      # 逐行成本累加
            m["qty"] += qty

        items = []
        for code in order:
            m = merged[code]
            # basic_rate 在 Stock Entry 里是「单位成本」，
            # 上面累加的是总成本，这里除回数量还原单位成本。
            m["basic_rate"] = round(m["basic_rate"] / m["qty"], 6) if m["qty"] else 0
            items.append(m)

        se = frappe.get_doc({
            "doctype": "Stock Entry",
            "stock_entry_type": "Material Receipt",
            "company": self.company,
            "posting_date": self.purchase_date or self.stock_datetime,
            "remarks": self.get_remarks(),
            "items": items,
        })
        se.flags.ignore_permissions = True
        se.insert()
        se.submit()

        self.db_set("stock_entry_ref", se.name)


        items = [{
            "item_code": r.serial_no.strip(),
            "qty": flt(self.qty) or 1,
            "warehouse": self.warehouse,
            "basic_rate": flt(r.total_cny),
            "cost_center": cost_center,
        } for r in rows]

        se = frappe.get_doc({
            "doctype": "Stock Entry",
            "stock_entry_type": "Material Receipt",
            "company": self.company,
            "posting_date": self.purchase_date or self.stock_datetime,
            "remarks": self.get_remarks(),
            "items": items,
        })
        se.flags.ignore_permissions = True
        se.insert()
        se.submit()

        self.db_set("stock_entry_ref", se.name)

    def get_remarks(self):
        rows = [r for r in (self.serial_numbers or []) if r.serial_no]
        codes = "、".join(r.serial_no for r in rows)
        return _("入库 {0} | {1} | {2}").format(
            codes,
            self.uom or "",
            self.get_title(),
        )

    def get_cost_center(self):
        cc = frappe.db.get_value("Company", self.company, "cost_center")
        return cc or _("Main - {0}").format(self.company)

    def on_cancel(self):
        self.cancel_stock_entry()

    def cancel_stock_entry(self):
        if not self.stock_entry_ref:
            return
        se = frappe.get_doc("Stock Entry", self.stock_entry_ref)
        if se.docstatus == 1:
            se.flags.ignore_permissions = True
            se.cancel()


@frappe.whitelist()
def get_recent_serials(search_term=None, start=0, page_len=20):
    """商品编号输入框的快捷提示 —— 最近录入过的编号。

    返回按最近使用时间倒序的编号列表，前端作为下拉候选。
    """
    return frappe.db.sql(
        """
        SELECT si.serial_no AS serial_no,
               si.manufacturer AS manufacturer,
               si.model AS model,
               si.specification AS specification,
               si.parent AS stock_in,
               si.parentcreation AS created
        FROM `tabStock In Item` si
        WHERE si.serial_no IS NOT NULL
          AND si.serial_no != ''
          AND (%(kw)s IS NULL OR si.serial_no LIKE %(kw)s)
        GROUP BY si.serial_no
        ORDER BY MAX(si.parentcreation) DESC
        LIMIT %(len)s OFFSET %(start)s
        """,
        {"kw": f"%{search_term}%" if search_term else None,
         "len": page_len, "start": start},
        as_dict=True,
    )
