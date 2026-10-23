"""把 Evidence Package.disassembly_note 改名为 customs_declaration

原因：证据包现在关联报关单（Customs Declaration）而不是拆解单，
因为一张报关单可能同时包含多个拆解单和散件采购单的货。

注意：DocType JSON 改名后，migrate 不会自动删旧列，
需要在这里显式 drop。
"""

import frappe


def execute():
    if not frappe.db.exists("DocType", "Evidence Package"):
        return

    cols = frappe.db.sql(
        "SHOW COLUMNS FROM `tabEvidence Package`", as_dict=True
    )
    names = {c["Field"] for c in cols}

    if "disassembly_note" in names:
        frappe.db.sql("ALTER TABLE `tabEvidence Package` DROP COLUMN `disassembly_note`")
        print("✓ 已删除旧列 disassembly_note")

    if "customs_declaration" not in names:
        frappe.db.sql(
            "ALTER TABLE `tabEvidence Package` "
            "ADD COLUMN `customs_declaration` varchar(140)"
        )
        print("✓ 已添加新列 customs_declaration")
