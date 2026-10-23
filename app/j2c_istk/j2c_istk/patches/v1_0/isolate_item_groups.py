"""主数据隔离：品类树挂到本项目自己的根节点下

多站点架构下，每个 site 是独立数据库，主数据天然物理隔离：
    Item / Item Group / UOM / Brand / Warehouse / Company / Serial No
全都在各自的库里，不会串。

但 Item Group 这棵树有个额外约定 —— 每个项目用自己的根节点名，
这样在共享视图（未来如果合并站点）或跨项目比价时，一眼能分清归属：
    J2C_ISTK  → 根节点「J2C_ISTK」
    C2J_ISTK  → 根节点「C2J_ISTK」

原来用的根节点是「二手电脑硬件」，改名为项目自己的标识。
子类（内存/显卡/CPU/...）保持不变，只改父级。

注意：
  - Item Group.name 是「<自身名> - <父级名>」拼出来的，改父级会改 name
  - Item.item_group 指向的是 name，必须同步更新
  - 已有 Item 会跟着换分类
"""

import frappe

PROJECT_ROOT = "J2C_ISTK"          # 本项目的品类根节点
OLD_ROOT = "二手电脑硬件"           # 原来的根节点


def execute():
    if not frappe.db.exists("Item Group", OLD_ROOT):
        # 可能已经改过了（幂等）
        if frappe.db.exists("Item Group", PROJECT_ROOT):
            print(f"- 根节点已是「{PROJECT_ROOT}」，检查子类")
        else:
            print(f"! 找不到根节点「{OLD_ROOT}」，且没有「{PROJECT_ROOT}」，跳过")
            return
    else:
        print(f"=== 品类树：{OLD_ROOT} → {PROJECT_ROOT} ===")

    old_root = OLD_ROOT if frappe.db.exists("Item Group", OLD_ROOT) else None

    # 1. 创建/复用新根节点
    # 根节点的父级是 Frappe 自动建的 "All Item Groups"
    all_root = frappe.db.get_value(
        "Item Group", {"item_group_name": "All Item Groups"}, "name"
    )
    new_root = frappe.db.get_value(
        "Item Group",
        {"item_group_name": PROJECT_ROOT, "parent_item_group": all_root},
        "name",
    )
    if not new_root:
        doc = frappe.get_doc(
            {
                "doctype": "Item Group",
                "item_group_name": PROJECT_ROOT,
                "parent_item_group": all_root,
                "is_group": 1,
            }
        )
        doc.insert(ignore_permissions=True)
        new_root = doc.name
        print(f"  + 新根节点: {new_root}")
    else:
        print(f"  = 新根节点已存在: {new_root}")

    if not old_root:
        frappe.db.commit()
        return

    # 2. 把旧根节点的直接子节点改挂到新根节点下
    #
    #    v16 的 Item Group.name 就是 item_group_name 本身（不拼父级）——
    #    实测：name='内存', item_group_name='内存', parent='二手电脑硬件'
    #    所以改父级不需要 rename，name 不变，Item 的引用也不用动。
    #
    #    （踩过的坑：一开始以为 name 会拼父级，用 rename_doc 改父级，
    #     结果报 "No changes made because old and new name are the same"）
    children = frappe.db.sql(
        "SELECT name FROM `tabItem Group` WHERE parent_item_group = %s",
        (old_root,),
    )

    for (child_name,) in children:
        if frappe.db.exists(
            "Item Group", {"item_group_name": child_name, "parent_item_group": new_root}
        ):
            print(f"  ! {child_name} 在新根下已存在，合并")
            frappe.db.sql(
                "UPDATE `tabItem` SET item_group = %s WHERE item_group = %s",
                (child_name, child_name),
            )
            frappe.delete_doc("Item Group", child_name, force=True, ignore_permissions=True)
            continue

        frappe.db.set_value(
            "Item Group", child_name, "parent_item_group", new_root
        )
        print(f"  ✓ {child_name}: parent {old_root} → {new_root}")

    frappe.db.commit()

    # 3. 删旧根节点（现在没有子节点了）
    if frappe.db.exists("Item Group", old_root):
        frappe.delete_doc("Item Group", old_root, force=True, ignore_permissions=True)
        frappe.db.commit()
        print(f"  ✓ 删除旧根节点: {old_root}")

    print(f"✓ 品类树已隔离到「{PROJECT_ROOT}」")


if __name__ == "__main__":
    execute()
