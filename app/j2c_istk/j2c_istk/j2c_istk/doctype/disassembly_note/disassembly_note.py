import frappe
from frappe import _
from frappe.model.document import Document

from j2c_istk.utils.cost_allocation import (
    allocate_by_reference_price,
    calculate_final_cost,
)
from j2c_istk.utils.label_generator import generate_serial_number

# 不参与成本分摊的处置方式（日本境内处理：拍卖 / 丢弃 / 拆件）
LOCAL_DISPOSITIONS = {"PartsOnly", "Scrap"}


class DisassemblyNote(Document):
    def autoname(self):
        """生成拆解单主键 YYMMDD-NN

        DocType 的 autoname 设为 "custom"，Frappe 会调用本方法，
        本方法必须给 self.name 赋值后 return。

        踩过的坑：
        1. 用 before_naming + set_new_name() 会被autoname:"naming_series:" 跳过，
           而且 set_new_name() 内部会再跑 before_naming → 无限递归。
        2. 此时 frappe.get_all / frappe.utils.format_date 都不可用
           （表未就绪 / locale 未初始化 → RecursionError），
           只能用 frappe.db.sql + strftime。
        """
        if self.name and "-" in str(self.name):
            return self.name

        d = frappe.utils.getdate(self.disassembly_date or frappe.utils.nowdate())
        prefix = d.strftime("%y%m%d")

        existing = frappe.db.sql(
            """
            SELECT name FROM `tabDisassembly Note`
            WHERE name LIKE %s
            ORDER BY name DESC
            LIMIT 1
            """,
            (prefix + "-%",),
        )
        seq = int(existing[0][0].split("-")[-1]) + 1 if existing else 1

        self.name = f"{prefix}-{seq:02d}"
        self.dn_name = self.name
        return self.name

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
        """按采购时参考价权重分摊整机成本到零件

        分摊规则：
          · disposition 为 PartsOnly / Scrap 的零件视为日本境内处理，
            不参与分摊，采购成本记 0（但保留参考价供后续处置记账）
          · 其余（Normal / SelfUse / ForRepair）按 market_ref_price_cny 权重分摊
          · 出口件参考价合计为 0 时退化为按件数均摊
        """
        if not self.items or not self.cny_cost:
            return

        # 已提交后不再重算（成本锁定）
        if self.docstatus == 1:
            return

        local_rows = [
            r for r in self.items if r.disposition in LOCAL_DISPOSITIONS
        ]
        export_rows = [
            r for r in self.items if r.disposition not in LOCAL_DISPOSITIONS
        ]

        # 境内处理件：成本归零（仍保留参考价）
        for row in local_rows:
            row.allocated_purchase_cost = 0.0
            row.final_cost = calculate_final_cost(row)

        if not export_rows:
            return

        total_ref = sum(
            frappe.utils.flt(r.market_ref_price_cny) for r in export_rows
        )

        if total_ref <= 0:
            per_item = frappe.utils.flt(self.cny_cost) / len(export_rows)
            for row in export_rows:
                row.allocated_purchase_cost = round(per_item, 2)
            frappe.msgprint(
                _("参考价为 0，已按件数均摊采购成本"), indicator="orange"
            )
        else:
            allocate_by_reference_price(
                [
                    {
                        "market_ref_price_cny": r.market_ref_price_cny,
                        "_target": _AllocTarget(r, "allocated_purchase_cost"),
                    }
                    for r in export_rows
                ],
                self.cny_cost,
            )

        for row in export_rows:
            row.final_cost = calculate_final_cost(row)

    # ---------------- SN 生成 ----------------

    def create_serial_numbers(self):
        """提交时生成 Serial No（v16 中 Serial Number 已更名为 Serial No）

        v16 的Serial No：
          · autoname = "field:serial_no"，即 name 取 serial_no 字段值
          · serial_no 是必填Data 字段
        """
        for row in self.items:
            # 境内处置件（PartsOnly / Scrap）不生成 SN——
            # 这类件在日本境内就处理掉了，不出口、不上架、不入库
            if row.disposition in LOCAL_DISPOSITIONS:
                continue

            if not row.serial_number:
                row.serial_number = generate_serial_number(
                    self.name, row.component_type, row.sequence_no or 1
                )

            if not frappe.db.exists(
                "Serial No", {"serial_no": row.serial_number}
            ):
                self._make_serial_no(row)

        # on_submit 阶段给子表行赋值后，Frappe 不会自动持久化
        # （save() 已在 run_post_save_methods 之前完成子表写入）。
        # 这里显式回写 serial_number，让物流批次/报关单能按 SN 查到零件。
        for row in self.items:
            if row.serial_number:
                frappe.db.set_value(
                    "Disassembly Note Item",
                    row.name,
                    "serial_number",
                    row.serial_number,
                    update_modified=False,
                )

    def _make_serial_no(self, row):
        """创建 Serial No 记录

        ERPNext v16 禁止新建的 Serial No 直接带 warehouse
        （仓库只能由 Stock Entry / Purchase Receipt 通过 Stock Ledger 设置），
        抛SerialNoCannotCreateDirectError。

        本项目的零件是「拆解产生」而非「采购入库」，所以：
          · SN 只作为零件身份标识，不绑定仓库
          · 库存在哪个仓、由哪批物流批次运来，靠拆解单 + 物流批次追踪
          · Serial No 自身不带 warehouse，后续如需入库用 Stock Transfer 处理
        """
        sn = frappe.get_doc(
            {
                "doctype": "Serial No",
                "serial_no": row.serial_number,
                "item_code": row.item,
                "company": self.company,
                "status": "Active",
                "posting_date": self.disassembly_date,
            }
        )
        sn.flags.ignore_permissions = True
        sn.flags.ignore_mandatory = True
        sn.insert(ignore_mandatory=True)


class _AllocTarget:
    """轻量适配器：让分摊函数能写入 Child DocType 字段

    分摊函数 allocate_by_reference_price 约定写入 target.allocated_cost，
    这里把它转发到真实子表行的指定字段（如 allocated_purchase_cost）。

    踩过的坑：
    1. 不能用 __slots__——__setattr__ 拦截后没有 allocated_cost 属性可存，
       object.__setattr__ 会直接抛 AttributeError。
    2. __init__ 里的 _doc/_attr 赋值必须走 object.__setattr__，
       否则会被自己的 __setattr__ 递归拦截。
    """

    def __init__(self, doc, attr):
        object.__setattr__(self, "_doc", doc)
        object.__setattr__(self, "_attr", attr)

    def __setattr__(self, key, value):
        if key == "allocated_cost":
            setattr(self._doc, self._attr, value)
        else:
            object.__setattr__(self, key, value)
