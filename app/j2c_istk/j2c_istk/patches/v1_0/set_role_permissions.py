"""给角色授予 DocType 权限"""

import frappe

ROLES = ["System Manager", "Stock User", "Stock Manager"]


def execute():
    doctypes = [
        "Disassembly Note",
        "Logistics Batch",
        "Customs Declaration",
        "Item Transit Record",
        "Market Price History",
        "Trade Settings",
        "Evidence Package",
    ]

    for doctype in doctypes:
        if not frappe.db.exists("DocType", doctype):
            print(f"  • {doctype} 尚未创建，跳过")
            continue

        for role in ROLES:
            existing = frappe.db.exists(
                "Custom DocPerm",
                {"parent": doctype, "role": role, "permlevel": 0},
            )
            if existing:
                continue
            perm = frappe.get_doc(
                {
                    "doctype": "Custom DocPerm",
                    "parent": doctype,
                    "role": role,
                    "permlevel": 0,
                    "read": 1,
                    "write": 1,
                    "create": 1,
                    "delete": 1,
                    "submit": 1,
                    "cancel": 1,
                    "amend": 1,
                    "report": 1,
                    "export": 1,
                    "share": 1,
                    "print": 1,
                    "email": 1,
                }
            )
            perm.insert(ignore_permissions=True)
        print(f"  ✓ 权限已授予: {doctype}")
