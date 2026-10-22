"""仓库改名与清理

改名（用户要求统一为简短名称）：
  JP-ISTK        → JP                日本物流仓
  JP-ISTK-LOCAL  → JP-LOCAL          日本公司留用仓

删除（用户确认「现在完全重建」，这些是早期测试仓库）：
  日本-ISTK / 在途物料 / 成品 / 进行中 / 仓库

注意：
1. Frappe 的 Warehouse name = "<abbr> - <warehouse_name>"，
   rename_doc 会自动更新 name，但所有引用它的地方
   （Stock Ledger、Serial No、Custom Field 默认值等）也必须跟着改。
2. 先处理子节点再处理父节点（仓库有树形结构），
   否则父节点改名后子节点的 parent 引用会断。
"""

import frappe

# (旧 warehouse_name, 新 warehouse_name)
RENAMES = [
    ("JP-ISTK", "JP"),
    ("JP-ISTK-LOCAL", "JP-LOCAL"),
]

# 早期测试仓库（用户确认「现在完全重建」）
#
# 注意：Frappe 会为每个 Company 自动创建两个系统仓库，不能删：
#   所有仓库— 是 parent root，所有 Warehouse 都挂在它下面
#   仓库     是默认收货仓库，Stock Entry 等单据会引用它
# 所以 OBSOLETE 只列真正的测试残留。
OBSOLETE = [
    ("日本-ISTK", "CSRH"),
    ("在途物料", "CSRH"),
    ("成品", "CSRH"),
    ("进行中", "CSRH"),
]


def execute():
    """改名 + 清理

    注意执行顺序：patches.txt 里 create_warehouses 在本 patch 之前，
    它用的是新名字（JP / JP-LOCAL），本 patch 负责把遗留的旧名改过来。
    两者都是幂等的，重复执行安全。
    """
    _rename_warehouses()
    _drop_obsolete()


def _rename_warehouses():
    """按 warehouse_name 找旧仓库并改名

    不硬编码完整的 Warehouse.name（"<abbr> - <name>"），
    因为 abbr 可能变（比如 Company 改名）。
    """
    for old_name, new_name in RENAMES:
        rows = frappe.db.sql(
            """
            SELECT name, company FROM `tabWarehouse`
            WHERE warehouse_name = %s
            """,
            (old_name,),
        )
        if not rows:
            print(f"- {old_name} 不存在，跳过")
            continue

        for full, company in rows:
            abbr = frappe.db.get_value("Company", company, "abbr")
            target = f"{abbr} - {new_name}"

            if full == target:
                print(f"- {full} 已是目标名")
                continue
            if frappe.db.exists("Warehouse", target):
                print(f"! 目标 {target} 已存在，跳过 {full}")
                continue

            # 必须用 rename_doc，不能用 db.set_value：
            # Warehouse.name 是主键，set_value 不会重算它，
            # 结果 warehouse_name 变了但 name 还是旧的（显示仍不对）。
            frappe.rename_doc(
                "Warehouse", full, new_name, force=True, merge=False
            )
            print(f"✓ {full} → {target}")


def _drop_obsolete():
    """删除早期测试仓库

    两个坑：
    1. 匹配条件不能写 name LIKE "% - <name>"——
       rename_doc 之后 name 格式可能变（"<abbr> - <name>" 或
       "<name> - <abbr>"），两种格式都要匹配。
       正确做法：直接按 warehouse_name 字段查。
    2. "仓库"和"所有仓库"是 Frappe 自动创建的系统仓库，不能删
       （所有仓库 是 parent root，仓库 是默认收货仓库）。
    """
    for wh_name, _company in OBSOLETE:
        rows = frappe.db.sql(
            """
            SELECT name, company FROM `tabWarehouse`
            WHERE warehouse_name = %s
            """,
            (wh_name,),
        )
        if not rows:
            continue

        for full, company in rows:
            # 保护 Frappe 系统仓库（删了会破坏仓库树/默认收货仓）
            if full in (f"CSRH - 仓库", f"CSRH - 所有仓库",
                        f"ISTK - 仓库", f"ISTK - 所有仓库"):
                print(f"- {full} 是 Frappe 系统仓库，保留")
                continue

            # 有 parent 是正常的（挂在"所有仓库"下面），
            # 只有「自己是别人 的 parent」才不能删——会留下孤儿子节点。
            children = frappe.db.sql(
                "SELECT COUNT(*) FROM `tabWarehouse` WHERE parent_warehouse = %s",
                (full,),
            )[0][0]
            if children:
                print(f"! {full} 有 {children} 个子仓库，跳过")
                continue

            has_stock = frappe.db.count(
                "Stock Ledger Entry", {"warehouse": full}
            )
            if has_stock:
                print(f"! {full} 有 {has_stock} 条库存流水，跳过")
                continue

            frappe.delete_doc(
                "Warehouse", full, force=True, ignore_permissions=True
            )
            print(f"✓ 删除 {full}")
