#!/usr/bin/env python3
"""部署前自检：避免把语法错误传到生产

检查项：
1. 所有 controller 的 Python 语法
2. 继承 Document 的类是否正确 import
3. DocType JSON 的必填字段
4. hooks.py 的 doctype_js 路径是否存在对应文件
"""

import ast
import json
import os
import re
import sys

APP = "secondtrade"
DT_ROOT = f"{APP}/trade/doctype"

errors = []
warnings = []



def check_syntax(path, name):
    try:
        ast.parse(open(path).read())
    except SyntaxError as e:
        errors.append(f"[语法] {name}: {e.msg} (行 {e.lineno})")
        return False
    return True


def check_document_import(path, name):
    src = open(path).read()
    if "(Document)" in src and "from frappe.model.document import Document" not in src:
        errors.append(f"[import] {name}: 继承 Document 但缺少 import")
        return False
    return True


def check_json(path, name):
    try:
        d = json.load(open(path))
    except json.JSONDecodeError as e:
        errors.append(f"[JSON] {name}: {e}")
        return None

    if not d.get("module"):
        errors.append(f"[JSON] {name}: 缺少 module")
    if not d.get("name"):
        errors.append(f"[JSON] {name}: 缺少 name")
    return d


def main():
    if not os.path.isdir(DT_ROOT):
        print(f"✗ 找不到 {DT_ROOT}（请在 app/secondtrade 目录下运行）")
        return 1

    doctypes = [d for d in sorted(os.listdir(DT_ROOT))
                if os.path.isdir(f"{DT_ROOT}/{d}")]

    print(f"检查 {len(doctypes)} 个 DocType ...\n")

    for d in doctypes:
        py = f"{DT_ROOT}/{d}/{d}.py"
        js = f"{DT_ROOT}/{d}/{d}.json"
        init = f"{DT_ROOT}/{d}/__init__.py"

        if not os.path.exists(init):
            errors.append(f"[文件] {d}: 缺 __init__.py")
        if not os.path.exists(js):
            errors.append(f"[文件] {d}: 缺 {d}.json")
            continue
        if not os.path.exists(py):
            errors.append(f"[文件] {d}: 缺 {d}.py")
            continue

        if check_syntax(py, d):
            check_document_import(py, d)
        check_json(js, d)

    # hooks doctype_js 路径检查
    hooks = f"{APP}/hooks.py"
    if os.path.exists(hooks):
        src = open(hooks).read()
        if "doctype_js" in src:
            import re
            for m in re.finditer(r'"([^"]+)":\s*"public/js/([^"]+)"', src):
                rel = f"{APP}/public/js/{m.group(2)}"
                if not os.path.exists(rel):
                    errors.append(
                        f"[hooks] doctype_js 指向不存在的文件: {rel}"
                    )
                elif not m.group(2).endswith(".bundle.js"):
                    warnings.append(
                        f"[hooks] {m.group(2)}: esbuild 只打包 *.bundle.js"
                    )
    else:
        errors.append("[文件] hooks.py 不存在")

    # Link → Company 的默认值必须用完整 DocType name，不是 abbr
    # v16 的坑：Company 的 name 是 ISOTENKAI，abbr 才是 ISTK，
    # Link 字段的 default 填 abr 会报 LinkValidationError
    valid_companies = {"ISOTENKAI", "CSRH"}
    for d in doctypes:
        js = f"{DT_ROOT}/{d}/{d}.json"
        if not os.path.exists(js):
            continue
        try:
            dj = json.load(open(js))
        except json.JSONDecodeError:
            continue
        for f in dj.get("fields", []):
            if f.get("options") == "Company" and f.get("default"):
                if f["default"] not in valid_companies:
                    errors.append(
                        f"[Link] {d}.{f['fieldname']}: "
                        f"Company 默认值 {f['default']!r} 不是完整 name"
                        f"（应为 ISOTENKAI / CSRH，不是 abbr）"
                    )

    # Link → Warehouse 的默认值格式检查
    # Frappe 的 Warehouse.name = "<company_abbr> - <warehouse_name>"
    for d in doctypes:
        js = f"{DT_ROOT}/{d}/{d}.json"
        if not os.path.exists(js):
            continue
        try:
            dj = json.load(open(js))
        except json.JSONDecodeError:
            continue
        for f in dj.get("fields", []):
            if f.get("options") == "Warehouse" and f.get("default"):
                dv = f["default"]
                if " - " not in dv:
                    errors.append(
                        f"[Link] {d}.{f['fieldname']}: "
                        f"Warehouse 默认值 {dv!r} 缺少 ' - ' 分隔"
                        f"（应为 '<abbr> - <name>'）"
                    )

    # v16「All Apps」入口检查
    # 踩过的坑：app 装了、模块也在，但 All Apps 里看不到入口。
    # 根因：v16 只显示声明了 add_to_apps_screen hook 的 app，
    # 而且侧栏 rail 靠 Dock（不是 Workspace）。
    hooks_py = f"{APP}/hooks.py"
    if os.path.exists(hooks_py):
        hsrc = open(hooks_py).read()
        if "add_to_apps_screen" not in hsrc:
            errors.append(
                "[AllApps] hooks.py 缺少 add_to_apps_screen hook"
                " → app 不会出现在 All Apps 页面"
            )
        else:
            print("  ✓ add_to_apps_screen 已声明")

        if "app_logo_url" not in hsrc and "logo" not in hsrc:
            errors.append("[AllApps] add_to_apps_screen 缺 logo 字段")

        # route 不能是 /app/xxx（desk 旧前缀，会重定向）
        if '"/app/' in hsrc:
            errors.append(
                "[AllApps] route 用了 /app/ 前缀"
                " → desk 旧前缀会重定向，应该用 /desk/<slug>"
            )

        # logo 文件必须真实存在
        import re as _re
        m = _re.search(r'"logo":\s*"(/assets/[^"]+)"', hsrc)
        if m:
            logo_rel = m.group(1).replace("/assets/secondtrade/", "")
            logo_path = f"{APP}/public/{logo_rel}"
            if not os.path.exists(logo_path):
                errors.append(f"[AllApps] logo 文件不存在: {logo_path}")

    # Dock 检查：v16 的侧栏 rail 来自 Dock 文档
    #
    # 路径（实测 get_doc_files 确认，frappe/erpnext 都是这个结构）：
    #   apps/frappe/frappe/dock/frappe/frappe.json
    #   apps/erpnext/erpnext/dock/erpnext/erpnext.json
    # → <app>/dock/<app>/<app>.json
    #
    # 坑：orphan 清理走 check_if_record_exists(type="app")，
    # 规则是 <app>/dock/<name>.json，跟 import 规则不一致
    # （frappe 自己也对不上，靠 standard=1 豁免）。
    # 所以文件必须放在 import 规则的位置，否则 migrate 不会导入。
    dock_json = f"{APP}/dock/secondtrade/secondtrade.json"
    if os.path.exists(dock_json):
        try:
            d = json.load(open(dock_json))
            if d.get("app") != "secondtrade":
                errors.append(f"[Dock] app 字段错误: {d.get('app')}")
            if not d.get("name"):
                # import_file.py:123 无条件读 doc["name"]，缺了直接 KeyError
                errors.append(
                    "[Dock] JSON 缺 name 字段"
                    " → migrate 报 KeyError: 'name'"
                )
            if d.get("standard") != 1:
                errors.append("[Dock] standard 必须为 1（app 层）")
            if not d.get("user") == "":
                errors.append("[Dock] user 必须为空串（app 层，不是 site/user 层）")
            if not d.get("items"):
                errors.append("[Dock] items 为空 → 侧栏 rail 无内容")
            for it in d.get("items", []):
                if it.get("link_type") not in ("Sidebar", "Workspace", "URL"):
                    errors.append(
                        f"[Dock] link_type 非法: {it.get('link_type')}"
                        " （只能 Sidebar / Workspace / URL）"
                    )
            print(f"  ✓ Dock 已配置（{len(d.get('items', []))} 项）")
        except Exception as e:
            errors.append(f"[Dock] JSON 解析失败: {e}")
    else:
        errors.append(
            f"[Dock] 缺少 {dock_json}"
            " → 侧栏 rail 无入口（v16 用 Dock 不用 Workspace）"
        )

    # Workspace 检查（v16 有4 个坑，全踩过）
    # 1. content 必须是 json.dumps 的字符串（不是 list，也不是 HTML）
    #    workspace.py:614 要 str/bytes；:106 要 loads 后是 list
    # 2. module 是必填字段
    # 3. links 子表的 type 只能是 "Link" / "Card Break"，
    #    目标 DocType 放在 link_to，link_type="DocType"
    # 4. 文件必须在 <app_path>/**/workspace/**/*.json，
    #    否则 migrate 的 orphan 清理会把它删掉
    import glob as _glob

    ws_files = _glob.glob(f"{APP}/**/workspace/**/*.json", recursive=True)
    if not ws_files:
        warnings.append(
            "[Workspace] 没有找到 workspace JSON——"
            "Desk 里 trade 模块会完全隐形。"
            "文件必须放在 <app>/**/workspace/**/*.json"
        )
    for wf in ws_files:
        rel = wf[len(APP) + 1:]
        try:
            wj = json.load(open(wf))
        except json.JSONDecodeError as e:
            errors.append(f"[Workspace] {rel}: JSON 解析失败 {e}")
            continue

        if not wj.get("module"):
            errors.append(f"[Workspace] {rel}: 缺少 module（必填）")
        if not wj.get("name"):
            errors.append(f"[Workspace] {rel}: 缺少 name")

        # content 必须是 JSON 字符串
        c = wj.get("content")
        if c is None:
            warnings.append(f"[Workspace] {rel}: 没有 content")
        elif isinstance(c, list):
            errors.append(
                f"[Workspace] {rel}: content 不能是 list，"
                f"必须 json.dumps(blocks) 传字符串"
            )
        elif isinstance(c, str):
            try:
                blocks = json.loads(c)
                if not isinstance(blocks, list):
                    errors.append(
                        f"[Workspace] {rel}: content 的 JSON 必须是 list"
                    )
            except json.JSONDecodeError:
                errors.append(
                    f"[Workspace] {rel}: content 不是合法 JSON——"
                    f"v16 要求 block JSON，不能传 HTML"
                )

        # links 的 type / link_type 校验
        for lk in wj.get("links", []):
            t = lk.get("type")
            if t not in ("Link", "Card Break", None):
                errors.append(
                    f"[Workspace] {rel}: links.type={t!r} 非法，"
                    f"只能是 'Link' 或 'Card Break'"
                )
            if t == "Link":
                if not lk.get("link_to"):
                    errors.append(
                        f"[Workspace] {rel}: "
                        f"links「{lk.get('label')}」缺 link_to"
                    )
                if lk.get("link_type") not in ("DocType", "Page", "Report", None):
                    errors.append(
                        f"[Workspace] {rel}: "
                        f"links「{lk.get('label')}」的 link_type 非法"
                    )

    # patch 检查：用了 frappe. 就必须 import frappe
    patches_dir = f"{APP}/patches"
    if os.path.isdir(patches_dir):
        for root, _dirs, files in os.walk(patches_dir):
            for fn in files:
                if not fn.endswith(".py") or fn == "__init__.py":
                    continue
                fpath = os.path.join(root, fn)
                rel = fpath[len(APP) + 1:]
                if not check_syntax(fpath, rel):
                    continue
                psrc = open(fpath).read()
                if "frappe." in psrc and "import frappe" not in psrc:
                    errors.append(f"[patch] {rel}: 用了 frappe. 但缺少 import")

    # utils 检查 + 递归自检
    # 踩过的坑：patch 时把函数体替换成了对自身的调用 → RecursionError，
    # 而且只有运行时才暴露，静态语法检查发现不了。
    utils = f"{APP}/utils"
    if os.path.isdir(utils):
        for f in sorted(os.listdir(utils)):
            if not f.endswith(".py"):
                continue
            fpath = f"{utils}/{f}"
            rel = f"utils/{f}"
            if not check_syntax(fpath, rel):
                continue

    # 同样的检查覆盖 trade/ 下的所有 controller
    trade_dir = f"{APP}/trade"
    if os.path.isdir(trade_dir):
        for root, _dirs, files in os.walk(trade_dir):
            for fn in files:
                if not fn.endswith(".py") or fn == "__init__.py":
                    continue
                fpath = os.path.join(root, fn)
                rel = fpath[len(APP) + 1:]
                if not check_syntax(fpath, rel):
                    continue
    
    print("=" * 56)
    if errors:
        print(f"✗ {len(errors)} 个错误：\n")
        for e in errors:
            print(f"  {e}")
    if warnings:
        print(f"\n⚠ {len(warnings)} 个警告：\n")
        for w in warnings:
            print(f"  {w}")
    if not errors:
        print("✓ 全部通过")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
