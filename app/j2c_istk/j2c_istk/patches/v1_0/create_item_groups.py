"""创建品类层级（Item Group）

品类用于行情价批量更新的分组：
    内存（每日更新）· 显卡（每日更新）
    CPU（不定时）· 存储（不定时）
    主板 / 电源 / 机箱（长周期）

v16 的 Item Group.name 就是 item_group_name 本身（实测：
name='内存', item_group_name='内存', parent='二手电脑硬件'），
不拼父级路径。

但为了稳妥（不同版本可能不同），这里仍然按层级顺序创建，
每建完一层就从数据库反查真实 name 传给下一层。

根节点的父级是 Frappe 自动建的 "All Item Groups"，
不能留空 —— 留空会变成孤立的顶层节点。
"""

import frappe

# 项目标识 —— 每个项目用自己的品类根节点名
# （J2C_ISTK / C2J_ISTK / ...），实现项目间的品类隔离。
# 多站点下主数据本来就物理隔离，这里是额外的语义标识，
# 让"这个品类属于哪个项目"一眼可辨。
PROJECT_ROOT = "J2C_ISTK"

TREE = [
    # (品类名, 父级键)  父级键用我们自己维护的映射，最后统一替换为真实 name
    (PROJECT_ROOT, None),
    ("内存", PROJECT_ROOT),
    ("DDR4", "内存"),
    ("DDR5", "内存"),
    ("显卡", PROJECT_ROOT),
    ("CPU", PROJECT_ROOT),
    ("主板", PROJECT_ROOT),
    ("存储", PROJECT_ROOT),
    ("电源", PROJECT_ROOT),
    ("机箱", PROJECT_ROOT),
]


def _find_by_group_name(group_name, parent_name):
    """按 item_group_name 查真实 DocType name（v16 会拼父级）"""
    filters = {"item_group_name": group_name}
    if parent_name:
        filters["parent_item_group"] = parent_name
    return frappe.db.get_value("Item Group", filters, "name")


def execute():
    created = 0
    resolved = {}  # 品类键 -> 真实 DocType name

    # 根节点的父级是 Frappe 自动建的 "All Item Groups"
    # （踩过的坑：传空串会让它变成孤立的顶层节点）
    all_root = frappe.db.get_value(
        "Item Group", {"item_group_name": "All Item Groups"}, "name"
    )
    if not all_root:
        print("! 找不到 All Item Groups，跳过品类初始化")
        return

    for group_name, parent_key in TREE:
        if parent_key is None:
            parent_real = all_root
        else:
            parent_real = resolved.get(parent_key)

        existing = _find_by_group_name(group_name, parent_real)
        if existing:
            resolved[group_name] = existing
            continue

        doc = frappe.get_doc(
            {
                "doctype": "Item Group",
                "item_group_name": group_name,
                "parent_item_group": parent_real,
                "is_group": 1,
            }
        )
        doc.insert(ignore_permissions=True)
        resolved[group_name] = doc.name
        created += 1
        print(f"  + {group_name}  ->  {doc.name}")

    frappe.db.commit()
    print(f"  品类: 新建 {created} / 共 {len(TREE)}")
