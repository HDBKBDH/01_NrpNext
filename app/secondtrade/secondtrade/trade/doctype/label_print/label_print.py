import frappe
from frappe import _
from frappe.model.document import Document

from secondtrade.utils.label_generator import build_label_payload, generate_qr_data_uri


class LabelPrint(Document):
    """标签打印工作台

    一个临时单据：选中单个 SN → 生成「文字标签（Tab 分隔）+ 二维码」，
    拷贝到 Brother P-touch Editor 直接排版打印。

    不用保存也能用，但保存后可留档（谁在什么时候给哪个 SN 打了标签）。
    """

    def validate(self):
        if not self.serial_no:
            return

        self._load_item()
        self._build_text()
        self._build_qr()

    # ---------------- 内部 ----------------
    #
    # 注意：这里刻意不提供任何 server method（如「生成标签文本」按钮）。
    #
    # 原因：Frappe v16 的 @frappe.whitelist() 在 DocType 方法上有 bug——
    #   frappe/__init__.py: whitelist() 内部
    #       fn = validate_argument_types(fn, apply_condition=...)  ← 新对象
    #       whitelisted.add(fn)                                     ← 注册新对象
    #   而 frappe/handler.py: run_doc_method 取
    #       fn = getattr(getattr(doc, method), "__func__", ...)     ← 原始函数
    #       is_whitelisted(fn)                                      ← 查原始函数
    #   两者 identity 不一致 → 白名单永远命中不了，必报 PermissionError。
    #
    # 前端改用 frm.refresh() / frm.save()（走 doc.run_method 的内部调用路径），
    # 不经过 whitelist 检查，也就不需要 @frappe.whitelist()。

    def _load_item(self):
        """从 Serial No 反查 Item 完整信息"""
        sn = frappe.db.get_value(
            "Serial No",
            self.serial_no,
            ["item_code", "status", "posting_date", "purchase_rate"],
            as_dict=True,
        )
        if not sn:
            frappe.throw(_("序列号不存在：{0}").format(self.serial_no))

        self.item_code = sn.item_code
        self.item_name = frappe.db.get_value("Item", sn.item_code, "item_name")

        # 零件明细（只读展示用）
        dni = frappe.db.get_value(
            "Disassembly Note Item",
            {"serial_number": self.serial_no},
            ["parent", "component_type", "condition_grade",
             "market_ref_price_cny", "final_cost"],
            as_dict=True,
        )
        if dni:
            self.sn_meta = (
                f"拆解单 {dni.parent} · 类型 {dni.component_type} · "
                f"成色 {dni.condition_grade or '-'} · "
                f"最终成本 {dni.final_cost:.2f} CNY"
            )
            self.item_meta = (
                f"采购时参考价 {dni.market_ref_price_cny:.2f} CNY"
            )
        else:
            self.sn_meta = f"SN {self.serial_no} · 状态 {sn.status}"
            self.item_meta = f"入库价 {sn.purchase_rate or 0:.2f} CNY"

    def _build_text(self):
        """生成 Tab 分隔的标签文本（Brother P-touch 表格格式）

        第 1 行是表头，第 2 行是数据——P-touch Editor 粘贴后
        会把两行分别当作表头行和数据行。
        """
        rows = [[self.item_name, self.serial_no]]
        if self.remark:
            rows[0].append(self.remark.strip())

        self.label_text = "\n".join("\t".join(r) for r in rows)

    def _build_qr(self):
        """生成 SN 二维码（Data URI，直接显示不落文件）"""
        try:
            self.qr_image = generate_qr_data_uri(self.serial_no)
        except Exception as e:
            # 二维码失败不阻塞文字标签
            frappe.msgprint(
                _("二维码生成失败：{0}（文字标签仍可正常使用）").format(e),
                indicator="orange",
            )