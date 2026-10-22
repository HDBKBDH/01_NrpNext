import json

import frappe
from frappe.model.document import Document


class EvidencePackage(Document):
    """整机退税证据包生成记录

    实际打包逻辑在 Phase 2 实现（需汇总多单据附件）
    """

    def on_submit(self):
        self.build_manifest()

    def build_manifest(self):
        """生成清单说明"""
        dn = frappe.get_doc("Disassembly Note", self.disassembly_note)
        lines = [
            f"拆解单：{dn.name}",
            f"采购单：{dn.purchase_receipt}",
            f"拆解日期：{dn.disassembly_date}",
            f"退税状态：{dn.tax_refund_status}",
            f"实际成本：{dn.cny_cost} CNY",
            "",
            "零件清单：",
        ]
        for row in dn.items:
            lines.append(
                f"  {row.serial_number} | {row.component_type} | {row.item}"
            )

        self.manifest = "\n".join(lines)
        self.file_count = len(dn.items)
        self.db_update()

    @staticmethod
    def build_zip(disassembly_note):
        """生成证据包 ZIP（Phase 2 实现）"""
        raise NotImplementedError("证据包打包将在 Phase 2 实现")
