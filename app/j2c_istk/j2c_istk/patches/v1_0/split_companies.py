"""拆分 Company：CSRH → CSRH / SY / HK / SZ / GOOFISH / TIKTOK

需求（用户确认）：
  BJ / SY / HK / SZ / GOOFISH / TIKTOK 各自作为独立 Company。
  仓库名暂不改（BJ-CSRH / BJ-SY / HK-01 / SZ-01 / GOOFISH / TIKTOK
  都是占位名，等真实名称确定后再改）。

映射（用户确认的最终版）：
  CSRH  ← BJ-CSRH                      China      CNY
  SY    ← BJ-SY                        China      CNY
  HK    ← HK-01 / HK-02 / HK-03       Hong Kong  CNY
  SZ    ← SZ-01                        China      CNY
  GF    ← GOOFISH → 改名 GF01          China      CNY
  TT    ← TIKTOK  → 改名 TT01          China      CNY

币种全部 CNY（用户要求：记账统一，汇率换算）。

注意 GF / TT 是新 Company 名（不是 GOOFISH / TIKTOK），
仓库名也从 GOOFISH / TIKTOK 改成 GF01 / TT01。

Frappe 的硬约束：
  - Warehouse.company 必填 → 拆 Company 才能拆仓库归属
  - 每个 Company 需要独立的 Account / Cost Center 体系
    （ERPNext 按 company 隔离）
  - Warehouse.name = "<warehouse_name> - <Company.abbr>"
    → 拆完 name 会变，rename_doc 会自动更新所有 Link 引用

注意：Company 的 abbr 决定了 name 后缀。
  CSRH 的 abbr 保持 CSRH（不拆的沿用）
  SY / HK / SZ / GOOFISH / TIKTOK 用同名 abbr

执行顺序：
  1. 先建新 Company（ERPNext 的 on_company_create 会建账套）
  2. 逐个搬仓库（先改 company，再 rename 让 name 跟着 abbr 走）
  3. 旧 CSRH 的「所有仓库」和「仓库」留在 CSRH
     （它们是 Frappe 的系统仓库，每个 Company 各有一套）
"""

import frappe


# (新 Company 名, abbr, country, {旧仓库名: 新仓库名})
# 新仓库名 = None 表示不改名
SPLIT = [
    ("SY", "SY", "China", {"BJ-SY": None}),
    ("HK", "HK", "Hong Kong", {"HK-01": None, "HK-02": None, "HK-03": None}),
    ("SZ", "SZ", "China", {"SZ-01": None}),
    ("GF", "GF", "China", {"GOOFISH": "GF01"}),
    ("TT", "TT", "China", {"TIKTOK": "TT01"}),
]

OLD_COMPANY = "CSRH"


def _ensure_company(name, abbr, country):
    """建 Company（幂等）

    ERPNext 的 Company 有 on_company_create，会自动建账套
    （Account / Cost Center / 会计年度等）。
    """
    if frappe.db.exists("Company", name):
        print(f"  = Company {name} 已存在")
        return

    doc = frappe.get_doc(
        {
            "doctype": "Company",
            "company_name": name,
            "abbr": abbr,
            "default_currency": "CNY",
            "country": country,
        }
    )
    doc.flags.ignore_permissions = True
    doc.insert(ignore_permissions=True)
    print(f"  + Company {name}（{country} / CNY）")


def execute():
    print("=== 拆分 Company ===")

    # 0. 原 CSRH 必须是 CNY / China
    if frappe.db.exists("Company", OLD_COMPANY):
        frappe.db.set_value("Company", OLD_COMPANY, "default_currency", "CNY")
        frappe.db.set_value("Company", OLD_COMPANY, "country", "China")

    # 1. 建新 Company
    for name, abbr, country, _warehouses in SPLIT:
        _ensure_company(name, abbr, country)
    frappe.db.commit()

    # 2. 搬仓库
    for name, abbr, country, warehouses in SPLIT:
        for old_wh_name, new_wh_name in warehouses.items():
            # 按 warehouse_name 找（name 会随 company 变化）
            rows = frappe.db.sql(
                """
                SELECT name, company FROM `tabWarehouse`
                WHERE warehouse_name = %s AND company = %s
                """,
                (old_wh_name, OLD_COMPANY),
            )
            if not rows:
                # 可能已经搬过了（用新名找）
                target_name = new_wh_name or old_wh_name
                rows = frappe.db.sql(
                    """
                    SELECT name, company FROM `tabWarehouse`
                    WHERE warehouse_name = %s AND company = %s
                    """,
                    (target_name, name),
                )
                if rows:
                    print(f"  - {target_name} 已在 {name}，跳过")
                    continue
                print(f"  ! 找不到仓库 {old_wh_name}，跳过")
                continue

            full, cur_company = rows[0]
            if cur_company == name:
                print(f"  - {old_wh_name} 已在 {name}，跳过")
                continue

            # 改 company
            #
            # 踩过的坑：set_value 改 company 后，Warehouse.name 不会自动重算！
            #   name 是主键（"<warehouse_name> - <Company.abbr>"），
            #   改 company 后必须显式 rename_doc 才会跟上新的 abbr。
            #   第一次跑完发现 name 还是 "BJ-SY - CSRH"（旧 abbr）。
            frappe.db.set_value("Warehouse", full, "company", name)
            frappe.db.commit()

            # 取改完后的真实 name
            cur = frappe.db.sql(
                "SELECT name FROM `tabWarehouse` WHERE warehouse_name = %s AND company = %s",
                (old_wh_name, name),
            )
            new_full = cur[0][0] if cur else full

            # 显式 rename，让 name 跟上新的 abbr
            expected_name = f"{old_wh_name} - {abbr}"
            if new_full != expected_name:
                if frappe.db.exists("Warehouse", expected_name):
                    print(f"  ! {expected_name} 已存在，跳过 rename {new_full}")
                else:
                    frappe.rename_doc(
                        "Warehouse", new_full, old_wh_name,
                        force=True, merge=False,
                    )
                    frappe.db.commit()
                    chk = frappe.db.sql(
                        "SELECT name FROM `tabWarehouse` WHERE warehouse_name=%s AND company=%s",
                        (old_wh_name, name),
                    )
                    new_full = chk[0][0] if chk else expected_name
                    print(f"    rename → {new_full}")

            # 改名（如果需要）
            #   同样要显式 rename_doc —— set_value 改 warehouse_name
            #   不会重算 name（主键）。
            if new_wh_name:
                target = f"{new_wh_name} - {abbr}"
                if frappe.db.exists("Warehouse", target):
                    print(f"  ! {target} 已存在，跳过改名")
                else:
                    frappe.rename_doc(
                        "Warehouse", new_full, new_wh_name,
                        force=True, merge=False,
                    )
                    frappe.db.commit()
                    chk = frappe.db.sql(
                        "SELECT name FROM `tabWarehouse` WHERE warehouse_name=%s AND company=%s",
                        (new_wh_name, name),
                    )
                    final = chk[0][0] if chk else target
                    print(f"  ✓ {old_wh_name} → {new_wh_name}"
                          f"（company {OLD_COMPANY} → {name}，name: {final}）")
            else:
                print(f"  ✓ {old_wh_name}: company {OLD_COMPANY} → {name}"
                      f"（name: {new_full}）")

    frappe.db.commit()

    # 3. 每个新 Company 需要自己的「所有仓库」root
    #    Frappe 不会自动建，要手动补
    for name, abbr, country, _w in SPLIT:
        root_name = f"所有仓库 - {abbr}"
        if not frappe.db.exists("Warehouse", root_name):
            # 先看有没有 warehouse_name='所有仓库' 且 company=name 的
            existing = frappe.db.sql(
                "SELECT name FROM `tabWarehouse` WHERE warehouse_name='所有仓库' AND company=%s",
                (name,),
            )
            if existing:
                print(f"  = {name} 的「所有仓库」已存在: {existing[0][0]}")
                continue

            doc = frappe.get_doc(
                {
                    "doctype": "Warehouse",
                    "warehouse_name": "所有仓库",
                    "company": name,
                    "is_group": 1,
                }
            )
            doc.flags.ignore_permissions = True
            doc.insert(ignore_permissions=True)
            print(f"  + {name} 的「所有仓库」: {doc.name}")

    frappe.db.commit()

    # 3.5 修 Trade Settings 的默认仓库
    #     仓库 name 随 company 变了，Link 引用 Frappe 会自动更新，
    #     但保险起见按 warehouse_name 重新对一次。
    ts = frappe.get_single("Trade Settings")
    for field, wh_name in (
        ("default_warehouse", "BJ-CSRH"),
        ("disassembly_warehouse", "JP"),
    ):
        cur = ts.get(field)
        if not cur:
            continue
        actual = frappe.db.get_value(
            "Warehouse", {"warehouse_name": wh_name}, "name"
        )
        if actual and actual != cur:
            frappe.db.set_value("Trade Settings", "Trade Settings", field, actual)
            frappe.db.commit()
            print(f"  ✓ Trade Settings.{field}: {cur} → {actual}")

    # 3.8 强制同步 name 和 parent_warehouse
    #
    # 踩过的坑（两次才修对）：
    #  1. set_value 改 company / warehouse_name 都不会重算 name
    #     （name 是主键 "<warehouse_name> - <Company.abbr>"）
    #  2. rename_doc 改 name 后，parent_warehouse 还指向旧的 root
    #     （因为 root 的 name 也变了）
    #
    # 所以这里直接用 SQL 同步（Link 字段是字符串，SQL 改最直接，
    # 且这些仓库引用计数都是 0，不会有历史单据受影响）。
    for name, abbr, country, warehouses in SPLIT:
        target_root = f"所有仓库 - {abbr}"
        if not frappe.db.exists("Warehouse", target_root):
            continue

        for old_wh_name, new_wh_name in warehouses.items():
            display = new_wh_name or old_wh_name
            expected = f"{display} - {abbr}"

            row = frappe.db.sql(
                """
                SELECT name FROM `tabWarehouse`
                WHERE warehouse_name = %s AND company = %s
                """,
                (display, name),
            )
            if not row:
                print(f"  ! 找不到 {display}（{name}），跳过")
                continue

            current = row[0][0]
            if current == expected:
                continue

            # 先改 name（主键，可能被引用）
            refs = []
            for tbl, col in (
                ("Stock Ledger Entry", "warehouse"),
                ("Bin", "warehouse"),
                ("Stock Entry Detail", "warehouse"),
                ("Loose Part Purchase", "warehouse"),
                ("Disassembly Note", "warehouse"),
                ("Serial No", "warehouse"),
            ):
                try:
                    n = frappe.db.count(tbl, {col: current})
                    if n:
                        refs.append(f"{tbl}={n}")
                except Exception:
                    pass

            if refs:
                print(f"  ! {current} 有引用 {refs}，跳过改名")
                continue

            frappe.db.sql(
                "UPDATE `tabWarehouse` SET name = %s WHERE name = %s",
                (expected, current),
            )
            print(f"  ✓ name: {current} → {expected}")

    frappe.db.commit()

    # 3.9 修 parent_warehouse（指向新 root）
    for name, abbr, country, warehouses in SPLIT:
        target_root = f"所有仓库 - {abbr}"
        for old_wh_name, new_wh_name in warehouses.items():
            display = new_wh_name or old_wh_name
            n = frappe.db.sql(
                """
                UPDATE `tabWarehouse` SET parent_warehouse = %s
                WHERE warehouse_name = %s AND company = %s
                  AND (parent_warehouse IS NULL OR parent_warehouse != %s)
                """,
                (target_root, display, name, target_root),
            )
            if n:
                print(f"  ✓ {display}: parent → {target_root}")

    frappe.db.commit()

    # 3.95 删除 ERPNext 为每个 Company 自动建的英文默认仓库
    #
    # ERPNext 建 Company 时会自动建一套：
    #   All Warehouses (root) + Stores + Work In Progress
    #   + Finished Goods + Goods In Transit
    # 我们用自己的「所有仓库」体系，这套英文的是冗余的。
    # 实测这 25 个全部零引用（Stock Ledger Entry / Bin / Stock Entry 都是 0）。
    #
    # 删之前必须先修 Company.default_warehouse
    # （它指向的 Stores - XX 马上就要被删，不改就成了悬空引用）
    #
    # 各 Company 的默认收货仓指向自己的第一个实体仓：
    #   CSRH        → BJ-CSRH
    #   SY          → BJ-SY
    #   HK          → HK-01
    #   SZ          → SZ-01
    #   GF          → GF01
    #   TT          → TT01
    #   ISOTENKAI   → JP
    DEFAULT_WAREHOUSE = {
        "CSRH": "BJ-CSRH",
        "SY": "BJ-SY",
        "HK": "HK-01",
        "SZ": "SZ-01",
        "GF": "GF01",
        "TT": "TT01",
        "ISOTENKAI": "JP",
    }

    print()
    print("=== 修 Company 默认仓库指向 ===")
    for co, wh_name in DEFAULT_WAREHOUSE.items():
        actual = frappe.db.get_value(
            "Warehouse", {"warehouse_name": wh_name, "company": co}, "name"
        )
        if not actual:
            print(f"  ! {co}: 找不到 {wh_name}，跳过")
            continue
        cur = frappe.db.get_value("Company", co, "default_warehouse")
        if cur == actual:
            continue
        frappe.db.set_value("Company", co, "default_warehouse", actual)
        frappe.db.commit()
        print(f"  ✓ {co}.default_warehouse: {cur!r} → {actual!r}")

    ENGLISH_DEFAULTS = (
        "Stores",
        "Work In Progress",
        "Finished Goods",
        "Goods In Transit",
    )
    for name, abbr, country, _w in SPLIT:
        # 先删子节点
        for en in ENGLISH_DEFAULTS:
            for (wn,) in frappe.db.sql(
                """
                SELECT name FROM `tabWarehouse`
                WHERE warehouse_name = %s AND company = %s
                """,
                (en, name),
            ):
                try:
                    frappe.delete_doc("Warehouse", wn, force=True, ignore_permissions=True)
                    print(f"  - 删除 {en} ({name})")
                except Exception as e:
                    print(f"  ! 删除 {en} ({name}) 失败: {e}")
        # 再删 root
        for (wn,) in frappe.db.sql(
            """
            SELECT name FROM `tabWarehouse`
            WHERE warehouse_name = 'All Warehouses' AND company = %s
            """,
            (name,),
        ):
            try:
                frappe.delete_doc("Warehouse", wn, force=True, ignore_permissions=True)
                print(f"  - 删除 All Warehouses ({name})")
            except Exception as e:
                print(f"  ! 删除 All Warehouses ({name}) 失败: {e}")
    frappe.db.commit()

    # 3.97 删除 ERPNext 建的默认收货仓「仓库」
    #
    # ERPNext 初始化时为最早的 Company 建一个 warehouse_name='仓库' 的默认收货仓，
    # 并写进 Company.default_warehouse。
    # 我们已有 BJ-CSRH / JP 等实体仓，这个是多余的。
    #
    # 前置条件（已在上一步把 default_warehouse 指向实体仓）：
    #   - 该仓零引用
    #   - 该仓没有子节点
    print()
    print("=== 删除多余的默认收货仓「仓库」===")
    for (wn,) in frappe.db.sql(
        "SELECT name FROM `tabWarehouse` WHERE warehouse_name = '仓库'"
    ):
        kids = frappe.db.sql(
            "SELECT COUNT(*) FROM `tabWarehouse` WHERE parent_warehouse = %s", (wn,)
        )[0][0]
        if kids:
            print(f"  ! {wn} 有 {kids} 个子仓库，跳过")
            continue

        refs = []
        for t in ("Stock Ledger Entry", "Bin", "Stock Entry Detail", "Serial No",
                  "Loose Part Purchase", "Disassembly Note"):
            try:
                c = frappe.db.count(t, {"warehouse": wn})
                if c:
                    refs.append(f"{t}={c}")
            except Exception:
                pass
        if refs:
            print(f"  ! {wn} 有引用 {refs}，跳过")
            continue

        # 确认没有 Company 指向它
        pointing = frappe.db.sql(
            "SELECT name FROM `tabCompany` WHERE default_warehouse = %s", (wn,)
        )
        if pointing:
            print(f"  ! {wn} 仍被 Company {pointing} 引用，跳过")
            continue

        frappe.delete_doc("Warehouse", wn, force=True, ignore_permissions=True)
        frappe.db.commit()
        print(f"  ✓ 删除 {wn}")

    # 4. 结果
    print()
    print("=== 结果 ===")
    for r in frappe.db.sql(
        """
        SELECT company, warehouse_name, name FROM `tabWarehouse`
        ORDER BY company, lft
        """
    ):
        print(f"  {r[0]:10s} {r[1]:12s} → {r[2]}")

    frappe.clear_cache()
    print("✓ 拆分完成")


if __name__ == "__main__":
    execute()
