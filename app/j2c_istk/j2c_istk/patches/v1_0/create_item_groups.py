"""创建品类层级（Item Group）

品类用于行情价批量更新的分组：
    内存（每日更新）· 显卡（每日更新）
    CPU（不定时）· 存储（不定时）
    主板 / 电源 / 机箱（长周期）

v16 的 Item Group.name 由「item_group_name - 父级」自动拼接，多级时形如
"二手电脑硬件 - 内存 - DDR4"，无法预先推断。
所以这里按层级顺序创建，每建完一层就从数据库反查真实 name 传给下一层。
"""

import frappe

TREE = [
    # (品类名, 父级键)  父级键用我们自己维护的映射，最后统一替换为真实 name
    ("二手电脑硬件", None),
    ("内存", "二手电脑硬件"),
    ("DDR4", "内存"),
    ("DDR5", "内存"),
    ("显卡", "二手电脑硬件"),
    ("CPU", "二手电脑硬件"),
    ("主板", "二手电脑硬件"),
    ("存储", "二手电脑硬件"),
    ("电源", "二手电脑硬件"),
    ("机箱", "二手电脑硬件"),
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

    for group_name, parent_key in TREE:
        parent_real = resolved.get(parent_key) if parent_key else None

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
