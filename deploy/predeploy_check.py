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

    # utils 检查
    utils = f"{APP}/utils"
    if os.path.isdir(utils):
        for f in sorted(os.listdir(utils)):
            if f.endswith(".py"):
                check_syntax(f"{utils}/{f}", f"utils/{f}")

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
