"""App 重命名：secondtrade → j2c_istk

Frappe 里 app 名出现在这些地方：
  - sites/apps.txt              （bench 层，已在部署时处理）
  - tabInstalled Application    （application 列）
  - tabModule Def.app_name
  - tabDock.app                 （v16 的侧栏）
  - tabWorkspace.module 对应的 app

注意：
  - tabInstalled Application.application 是主键，改它等于换 app。
    Frappe 之后会认为 j2c_istk 是新 app，需要重新 install。
    更好的做法：保留 tabInstalled Application 里的 secondtrade 记录，
    但那样 app_data 里就还是 secondtrade。

  权衡：用户要求 app 名统一为 j2c_istk。
  Frappe v16 的 app 层结构（add_to_apps_screen / Dock）都按 app 名索引，
  所以必须让 tabInstalled Application 里是 j2c_istk。

  执行顺序：
    1. 先把 Module Def.app_name、tabDock.app 等指向改掉
    2. 再改 tabInstalled Application.application（主键）
    3. 最后删掉旧的 secondtrade 记录（如果还需要的话——不需要，
       改名后旧记录已不存在）

  风险：改 tabInstalled Application 主键后，bench --site xxx migrate
  可能认为 app 未安装。本 patch 在 migrate 的 post_model_sync 阶段跑，
  跑完后需要重新 install-app j2c_istk（幂等）。
"""

import frappe


def execute():
    print("=== App 重命名 secondtrade → j2c_istk ===")

    # 1. Module Def.app_name
    n = frappe.db.sql(
        "UPDATE `tabModule Def` SET app_name = %s WHERE app_name = %s",
        ("j2c_istk", "secondtrade"),
    )
    if n:
        print(f"✓ Module Def: {n} 行 app_name → j2c_istk")

    # 2. Dock：name 是主键（= app 名），app 字段也指向它
    #    用 rename_doc 保证所有指向 Dock.name 的 Link 一起更新
    if frappe.db.table_exists("Dock"):
        for d in frappe.get_all(
            "Dock", filters={"app": "secondtrade"}, fields=["name"]
        ):
            old_name = d["name"]
            if frappe.db.exists("Dock", "j2c_istk"):
                frappe.db.sql(
                    "UPDATE `tabDock` SET app = %s WHERE name = %s",
                    ("j2c_istk", old_name),
                )
                frappe.db.sql(
                    "DELETE FROM `tabDock` WHERE name = %s", (old_name,)
                )
                print(f"✓ Dock: {old_name} 已合并到 j2c_istk")
            else:
                frappe.rename_doc(
                    "Dock", old_name, "j2c_istk", force=True, merge=False
                )
                print(f"✓ Dock: {old_name} → j2c_istk")

        # rename_doc 只改 name，不改 app 字段（app 是 Autocomplete 不是 Link）
        n = frappe.db.sql(
            "UPDATE `tabDock` SET app = %s WHERE app = %s",
            ("j2c_istk", "secondtrade"),
        )
        if n:
            print(f"✓ Dock: {n} 行 app → j2c_istk")

    # 3. Installed Application（app_name 列，name 是随机 hash 不用改）
    #    注意：列名是 app_name 不是 application（v16 改过）
    row = frappe.db.sql(
        "SELECT name, app_name, app_version FROM `tabInstalled Application`"
        " WHERE app_name = %s",
        ("secondtrade",),
    )
    if row:
        print(f"  Installed Application: {row[0]}")
        frappe.db.sql(
            "UPDATE `tabInstalled Application` SET app_name = %s"
            " WHERE app_name = %s",
            ("j2c_istk", "secondtrade"),
        )
        print("✓ Installed Application: secondtrade → j2c_istk")
    else:
        print("- Installed Application 里没有 secondtrade，跳过")

    # 4. 其他可能有 app_name 的表
    for table in ("Workspace", "DocType", "Custom Field", "Property Setter"):
        if not frappe.db.table_exists(table):
            continue
        # SHOW COLUMNS 返回 tuple（不是 dict），取第 0 列是 Field 名
        cols = {c[0] for c in frappe.db.sql(f"SHOW COLUMNS FROM `tab{table}`")}
        if "app_name" not in cols:
            continue
        n = frappe.db.sql(
            f"UPDATE `tab{table}` SET app_name = %s WHERE app_name = %s",
            ("j2c_istk", "secondtrade"),
        )
        if n:
            print(f"✓ {table}: {n} 行 app_name → j2c_istk")

    # 5. Patch Log 里的旧 app 前缀（secondtrade. → j2c_istk.）
    #    这样旧的 patch 记录不会重复执行
    n = frappe.db.sql(
        "UPDATE `tabPatch Log` SET patch = REPLACE(patch, %s, %s)"
        " WHERE patch LIKE %s",
        (
            "secondtrade.",
            "j2c_istk.",
            "secondtrade.%",
        ),
    )
    if n:
        print(f"✓ Patch Log: {n} 条前缀已更新")

    frappe.db.commit()
    frappe.clear_cache()
    print("✓ 完成")


if __name__ == "__main__":
    execute()
