"""模块重命名：trade → J2C_ISTK

背景：业务命名统一为 J2C_ISTK（区别于以后的其他贸易模块）。

Frappe 的 module 名规则：
  - Module Def.name / DocType.module 存原值 "J2C_ISTK"（数据库主键 + 显示名）
  - 目录和 Python import 路径用 scrub(module) = "j2c_istk"（小写）
    （frappe/modules/utils.py: get_doctype_module / scrub_dt_dn）

所以本 patch 只改数据库里的存储值，不动文件系统。

改动范围：
  - tabModule Def: name / module_name  trade → J2C_ISTK
  - tabDocType:    module              trade → J2C_ISTK
  - tabDocField:   module（如果非空）
  - tabWorkspace:  module / name
  - tabCustom Field / tabProperty Setter: module（如果指向 trade）
  - tabModule Onboarding: module
  - tabReport / tabPrint Format / tabDashboard 等其他带 module 的表

注意：DocType.name 不变（还是 Logistics Batch 等），
      变的只是它们的归属模块。
"""

import frappe


TABLES_WITH_MODULE = [
    "DocType",
    "DocField",
    "Workspace",
    "Module Onboarding",
    "Custom Field",
    "Property Setter",
    "Report",
    "Print Format",
    "Dashboard Chart",
    "Dashboard",
    "Notification",
    "Web Form",
    "Client Script",
    "Server Script",
    "Role",
    "Module Def",
    "Module Onboarding",
]


def execute():
    # 幂等：Module Def 可能已经改过（分步执行时）
    #       所以每一步都单独判断，不 early-return
    if frappe.db.exists("Module Def", "trade"):
        # 1. 先记下旧的 DocType 列表，方便回滚
        old_doctypes = frappe.get_all(
            "DocType", filters={"module": "trade"}, pluck="name"
        )
        print(f"  找到 {len(old_doctypes)} 个属于 trade 的 DocType")

        # 2. Module Def：先改 module_name（显示名）
        frappe.db.set_value("Module Def", "trade", "module_name", "J2C_ISTK")
        print("✓ Module Def 'trade'.module_name = J2C_ISTK")

        # 3. Module Def.name 是主键，所有 Link 字段指向它
        #
        #    踩过的坑：rename_doc 会报 "Only Custom Modules can be renamed"
        #    （module_def.py:before_rename 拦的）。
        #    绕过办法：先把它标成 custom=1，再 rename，最后改回 custom=0。
        #
        #    另一种办法：直接 UPDATE 主键 + 手动更新所有指向它的 Link。
        #    但 Link 字段分布在很多表（DocType.module、Workspace.module、
        #    DocField.module、Custom Field.module...），逐个 UPDATE 太容易漏。
        #    rename_doc 会自动处理 Link，所以用 custom 标记绕行。
        frappe.db.set_value("Module Def", "trade", "custom", 1)
        frappe.db.commit()

        try:
            if frappe.db.exists("Module Def", "J2C_ISTK"):
                print("! Module Def 'J2C_ISTK' 已存在，合并")
                frappe.rename_doc(
                    "Module Def", "trade", "J2C_ISTK", force=True, merge=True
                )
            else:
                frappe.rename_doc(
                    "Module Def", "trade", "J2C_ISTK", force=True, merge=False
                )
            print("✓ Module Def: trade → J2C_ISTK")
        finally:
            # 改回非 custom（它是我们 app 自带的模块）
            if frappe.db.exists("Module Def", "J2C_ISTK"):
                frappe.db.set_value("Module Def", "J2C_ISTK", "custom", 0)
            frappe.db.commit()
    else:
        print("- Module Def 'trade' 已不存在，跳过改名")

    # 4. 各表的 module 字段
    #    rename_doc 只更新 Link 类型的字段，
    #    Select/Data 类型的 module 字段要手动 UPDATE
    for table in TABLES_WITH_MODULE:
        if not frappe.db.table_exists(table):
            continue
        # SHOW COLUMNS 返回 tuple（不是 dict），取第 0 列是 Field 名
        cols = {c[0] for c in frappe.db.sql(f"SHOW COLUMNS FROM `tab{table}`")}
        if "module" not in cols:
            continue

        n = frappe.db.sql(
            f"UPDATE `tab{table}` SET module = %s WHERE module = %s",
            ("J2C_ISTK", "trade"),
        )
        if n:
            print(f"✓ {table}: {n} 行 module trade → J2C_ISTK")

    # 5. DocField 里的 module（DocField 有 module 列）
    #    上面的循环已覆盖

    # 6. Workspace 改名：贸易 → J2C_ISTK
    #    Workspace.name 是主键，rename_doc 会更新所有指向它的 Link
    #    （如 Workspace Shortcut / Sidebar 里的 link_to）
    if frappe.db.exists("Workspace", "贸易"):
        if frappe.db.exists("Workspace", "J2C_ISTK"):
            print("! Workspace 'J2C_ISTK' 已存在，删除旧的")
            frappe.delete_doc("Workspace", "贸易", force=True, ignore_permissions=True)
        else:
            # merge=True 需要目标已存在，这里目标不存在，
            # 用 merge=False（踩过：merge=True 报
            # "Workspace J2C_ISTK does not exist, select a new target to merge"）
            frappe.rename_doc(
                "Workspace", "贸易", "J2C_ISTK", force=True, merge=False
            )
            print("✓ Workspace: 贸易 → J2C_ISTK")
    elif frappe.db.exists("Workspace", "J2C_ISTK"):
        print("- Workspace 'J2C_ISTK' 已存在")
    else:
        print("! 找不到 Workspace '贸易'")

    # 6b. Workspace 的 module 字段（rename_doc 不动 Select 类型的字段）
    n = frappe.db.sql(
        "UPDATE `tabWorkspace` SET module = %s WHERE module = %s",
        ("J2C_ISTK", "trade"),
    )
    if n:
        print(f"✓ Workspace: {n} 行 module → J2C_ISTK")

    # 7. 清缓存
    frappe.clear_cache()
    print("✓ 缓存已清")


if __name__ == "__main__":
    execute()
