import frappe
from frappe import _
from frappe.model.document import Document

# 整机拆件的处置方式（日本境内处理，不出口不报关）
LOCAL_DISPOSITIONS = {"PartsOnly", "Scrap"}


class CustomsDeclaration(Document):
    """日本出境报关单

    整机拆件和直接采购的散件在同一张报关单里，不区分入口——
    用户视角只是「报这批货」。明细行会显示源单号便于追溯。

    金额一律以日元为准（报关合规要求），
    人民币只在子表里做内部记账，不显示在报关单上。
    """

    def validate(self):
        self.set_model_names()
        self.calculate_totals()
        self.validate_no_duplicates()

    def on_submit(self):
        # 注意：这里不生成 SN
        # 整机拆件的 SN 在拆解单提交时生成
        # 散件的 SN 在散件采购单提交时生成
        # 报关只是「申报」，不产生新的商品身份
        self.generate_evidence_package()

    # ---------------- 计算 ----------------

    def set_model_names(self):
        """型号全称带出"""
        for row in self.items:
            if row.item and not row.model_name:
                row.model_name = frappe.db.get_value("Item", row.item, "item_name")

    def calculate_totals(self):
        """汇总申报总值（日元）和件数

        报关单只认日元——CNY 换算全部在子表里做（隐藏字段），
        报关单上不显示任何人民币金额。
        """
        total_jpy = 0.0
        count = 0

        for row in self.items:
            qty = frappe.utils.flt(row.quantity or 1)
            price_jpy = frappe.utils.flt(row.declared_price_jpy)

            row.declared_amount_jpy = round(price_jpy * qty, 2)
            total_jpy += row.declared_amount_jpy
            count += qty

            # 子表内部记账（隐藏，不出现在报关单上）
            cny_price = frappe.utils.flt(row.declared_price_cny)
            if not cny_price and row.actual_cost_cny:
                cny_price = round(frappe.utils.flt(row.actual_cost_cny) / qty, 2)
            row.declared_price_cny = cny_price
            row.declared_amount_cny = round(cny_price * qty, 2)

        self.total_declared_jpy = round(total_jpy, 2)
        self.item_count = count

    def validate_no_duplicates(self):
        """同一报关单内 SN 不可重复（散件无 SN 则跳过）"""
        serials = [r.serial_number for r in self.items if r.serial_number]
        dupes = {s for s in serials if serials.count(s) > 1}
        if dupes:
            frappe.throw(
                _("序列号重复：{0}").format(", ".join(sorted(dupes))),
                title=_("重复序列号"),
            )

    # ---------------- 商品抓取 ----------------

    @frappe.whitelist()
    def get_parts_from_disassembly(self, disassembly_note):
        """从拆解单抓取可报关零件（整机拆件走这条路，有 SN）"""
        if not disassembly_note:
            frappe.throw(_("请先选择拆解单"))

        rows = frappe.get_all(
            "Disassembly Note Item",
            filters={
                "parent": disassembly_note,
                "docstatus": 1,
                "disposition": ("not in", list(LOCAL_DISPOSITIONS)),
            },
            fields=[
                "name", "parent", "serial_number", "item", "component_type",
                "condition_grade", "final_cost", "images",
            ],
            order_by="component_type asc, sequence_no asc",
        )

        if not rows:
            frappe.throw(_("该拆解单没有可报关的出口零件"))

        return self.add_customs_items(rows, source_type="Disassembly")

    @frappe.whitelist()
    def get_parts_from_purchase(self, loose_part_purchase):
        """从散件采购单抓取零件（直接采购的配件走这条路）"""
        if not loose_part_purchase:
            frappe.throw(_("请先选择散件采购单"))

        doc = frappe.get_doc("Loose Part Purchase", loose_part_purchase)
        rows = [
            {
                "serial_number": r.serial_number,
                "item": r.item,
                "component_type": r.component_type,
                "condition_grade": r.condition_grade,
                "purchase_price_jpy": r.unit_price_jpy,
                "images": r.image,
                "source_doc": loose_part_purchase,
            }
            for r in doc.items
        ]

        if not rows:
            frappe.throw(_("该采购单没有商品明细"))

        return self.add_customs_items(rows, source_type="LoosePurchase")

    def add_customs_items(self, rows, source_type):
        """把来源单的商品加进报关单明细

        rows: 统一结构，含 item / serial_number / 图片 / 成本信息
        """
        existing_sn = {r.serial_number for r in self.items if r.serial_number}
        existing_items = {r.item for r in self.items}

        added = 0
        skipped = 0

        for src in rows:
            sn = src.get("serial_number")
            item = src.get("item")
            if not item:
                continue

            # 整机拆件按 SN 去重；散件按型号去重
            if sn:
                if sn in existing_sn:
                    skipped += 1
                    continue
            elif item in existing_items:
                skipped += 1
                continue

            row = self.append("items")

            row.source_type = source_type
            row.source_doc = src.get("parent") or src.get("source_doc")

            row.serial_number = sn or ""
            row.item = item
            row.component_type = src.get("component_type")
            row.condition_grade = src.get("condition_grade")
            row.quantity = 1

            # 申报价：散件直接用采购日元单价；拆解件按分摊成本反推
            price_jpy = src.get("purchase_price_jpy")
            if not price_jpy:
                cost_cny = frappe.utils.flt(src.get("final_cost"))
                rate = frappe.db.get_single_value(
                    "Trade Settings", "jpy_reference_rate"
                )
                if cost_cny and rate:
                    price_jpy = round(cost_cny / rate, 0)
            row.declared_price_jpy = price_jpy or 0

            # 内部记账
            row.actual_cost_cny = frappe.utils.flt(src.get("final_cost"))

            # 图片：拆解件带拆解时的照片
            img = src.get("images")
            if isinstance(img, list):
                img = img[0] if img else None
            row.image = img

            existing_items.add(item)
            if sn:
                existing_sn.add(sn)
            added += 1

        self.set_model_names()
        self.calculate_totals()

        if skipped:
            frappe.msgprint(
                _("已跳过 {0} 条（该报关单已有相同商品）").format(skipped),
                indicator="orange",
            )

        return {"added": added, "skipped": skipped, "total": len(self.items)}

    # ---------------- 提交时 ----------------


    def generate_evidence_package(self):
        """生成退税证据包（ZIP：清单 CSV + 所有零件图 + 到岸凭证）"""
        from secondtrade.utils.evidence_builder import build_evidence_package

        pkg_name = build_evidence_package(self)
        self.evidence_package = pkg_name

        # on_submit 阶段给本单字段赋值后不会自动持久化
        # （save() 已在 run_post_save_methods 之前完成写入），
        # 必须显式回写，否则 reload 后是 None。
        frappe.db.set_value(
            "Customs Declaration",
            self.name,
            "evidence_package",
            pkg_name,
            update_modified=False,
        )