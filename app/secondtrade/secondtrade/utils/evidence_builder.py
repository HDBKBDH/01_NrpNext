"""退税证据包生成

用途：同一整机（或同一批货）的配件要能单独整理输出，
     方便走日本退税的证据链。

ZIP 结构：
    manifest.csv            商品清单（序号/型号/SN/来源单号/申报价/图片文件名）
    images/                 所有零件图（从拆解单或采购单带过来）
    documents/              到岸凭证、报关凭证
    README.txt              说明文字（本次报关信息、汇总金额）
"""

import csv
import io
import os
import zipfile

import frappe


def build_evidence_package(declaration):
    """为报关单生成证据包，返回 Evidence Package 的 name

    declaration: Customs Declaration 文档对象
    """
    if not declaration.items:
        frappe.throw("报关单没有商品明细，无法生成证据包")

    buf = io.BytesIO()

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        manifest_rows = _build_manifest(declaration)
        _write_manifest(zf, manifest_rows)
        _write_images(zf, declaration, manifest_rows)
        _write_documents(zf, declaration)
        _write_readme(zf, declaration, manifest_rows)

    buf.seek(0)
    payload = buf.getvalue()
    file_count = sum(1 for r in manifest_rows if r.get("_file_added"))

    # 先建记录（File 要挂在已存在的文档上，顺序不能反）
    pkg = frappe.get_doc(
        {
            "doctype": "Evidence Package",
            "customs_declaration": declaration.name,
            "company": declaration.company,
            "generated_at": frappe.utils.now(),
            "generated_by": frappe.session.user,
            "file_count": file_count,
            "manifest": _manifest_summary(declaration),
        }
    ).insert(ignore_permissions=True)

    # 再挂 ZIP
    pkg.package_file = _attach_zip(pkg.name, declaration, payload)
    pkg.flags.ignore_permissions = True
    pkg.save(ignore_permissions=True)

    return pkg.name


# ---------------- 清单 ----------------

def _build_manifest(declaration):
    """生成清单行，同时记录每行的图片文件名"""
    rows = []
    for idx, r in enumerate(declaration.items, start=1):
        img_file = r.image or ""
        rows.append(
            {
                "序号": idx,
                "源单号": r.source_doc or "",
                "来源": "整机拆件" if r.source_type == "Disassembly" else "散件采购",
                "类型": r.component_type or "",
                "型号编码": r.item or "",
                "型号全称": r.model_name or "",
                "序列号": r.serial_number or "",
                "成色": r.condition_grade or "",
                "数量": r.quantity or 1,
                "申报单价(JPY)": r.declared_price_jpy or 0,
                "申报金额(JPY)": r.declared_amount_jpy or 0,
                "图片": os.path.basename(img_file) if img_file else "",
                "_image": img_file,
                "_file_added": False,
            }
        )
    return rows


def _write_manifest(zf, rows):
    """写 manifest.csv（UTF-8 BOM，Excel 打开不乱码）"""
    if not rows:
        return

    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=[k for k in rows[0] if not k.startswith("_")],
        extrasaction="ignore",
    )
    writer.writeheader()
    writer.writerows(rows)

    # BOM 让Excel 正确识别 UTF-8
    zf.writestr("manifest.csv", b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8"))


# ---------------- 图片 ----------------

def _write_images(zf, declaration, rows):
    """把每件商品的图片打进ZIP/images/"""
    for row in rows:
        path = row.get("_image")
        if not path:
            continue

        data = _read_file(path)
        if not data:
            continue

        ext = os.path.splitext(path)[1] or ".jpg"
        name = f"images/{row['序号']:03d}_{row['序号']:03d}{ext}"

        # 重名时加序号
        sn = row.get("序列号")
        if sn:
            name = f"images/{row['序号']:03d}_{sn}{ext}"

        zf.writestr(name, data)
        row["图片"] = os.path.basename(name)
        row["_file_added"] = True


def _read_file(attached_path):
    """读 Frappe 内部文件（返回 bytes，失败返回 None）

    注意：ERPNext v16 的 File 表已删除 file_path /content 等列，
    不能再用 db.get_value("File", ..., "file_path") 拿物理路径。
    正确做法是用 File doctype 的 get_content()。
    """
    if not attached_path:
        return None

    # 1. 先按 file_url 直接查File 记录
    try:
        name = frappe.db.get_value("File", {"file_url": attached_path}, "name")
    except Exception:
        name = None

    if not name:
        # 2. Attach 字段有时存的是 file_url 前缀不全，用文件名兜底
        try:
            base = os.path.basename(attached_path.split("?")[0])
            name = frappe.db.get_value("File", {"file_name": base}, "name")
        except Exception:
            name = None

    if not name:
        return None

    # 3. 用 File doctype 读内容
    try:
        return frappe.get_doc("File", name).get_content()
    except Exception:
        return None


# ---------------- 单据 ----------------

def _write_documents(zf, declaration):
    """打进岸凭证、报关凭证"""
    for field, folder in (
        ("evidence_files", "documents"),
        ("hk_arrival_files", "documents"),
    ):
        paths = declaration.get(field) or []
        if isinstance(paths, str):
            paths = [paths]
        if not paths:
            continue

        for p in paths:
            data = _read_file(p)
            if not data:
                continue
            fname = os.path.basename(p)
            zf.writestr(f"{folder}/{folder}_{fname}", data)


# ---------------- 说明 ----------------

def _write_readme(zf, declaration, rows):
    """写README.txt，说明这批货的来龙去脉"""
    by_source = {}
    for r in rows:
        key = r["源单号"] or "(无)"
        by_source.setdefault(key, []).append(r)

    lines = [
        "日本中古电脑零件 · 退税证据包",
        "=" * 48,
        "",
        f"报关单号：{declaration.declaration_no or declaration.name}",
        f"报关日期：{declaration.declaration_date}",
        f"报关类型：{declaration.declaration_type}",
        f"出境口岸：{declaration.port or '-'}",
        f"申报总值：{declaration.total_declared_jpy:,.0f} 日元",
        f"件数：{declaration.item_count}",
        f"退税状态：{declaration.tax_refund_status}",
        "",
        f"到岸日期：{declaration.hk_arrival_date or '-'}",
        f"到岸单号：{declaration.hk_arrival_doc_no or '-'}",
        "",
        "源单明细",
        "-" * 48,
    ]

    for source, items in by_source.items():
        amount = sum(i["申报金额(JPY)"] for i in items)
        lines.append(f"  {source}：{len(items)} 件，合计 {amount:,.0f} 日元")

    lines += [
        "",
        "目录结构",
        "-" * 48,
        "  manifest.csv    商品清单（Excel 可直接打开）",
        "  images/          每件商品的实物照片",
        "  documents/       报关凭证与到岸凭证",
        "  README.txt       本文件",
        "",
        f"生成时间：{frappe.utils.now()}",
        f"生成人：{frappe.session.user}",
    ]

    zf.writestr("README.txt", "\n".join(lines))


def _manifest_summary(declaration):
    """报关单概要（存进 Evidence Package 的 manifest 字段）

    注意：frappe.utils.as_text 在 v16 已移除，
    这里手工拼一个可读的文本。
    """
    rows = [
        ("报关单号", declaration.declaration_no or declaration.name),
        ("报关日期", declaration.declaration_date),
        ("报关类型", declaration.declaration_type),
        ("出境口岸", declaration.port or "-"),
        ("申报总值", f"{declaration.total_declared_jpy:,.0f} 日元"),
        ("件数", declaration.item_count),
        ("退税状态", declaration.tax_refund_status),
        ("到岸日期", declaration.hk_arrival_date or "-"),
        ("到岸单号", declaration.hk_arrival_doc_no or "-"),
    ]
    width = max(len(r[0]) for r in rows)
    return "\n".join(f"{k.ljust(width)} : {v}" for k, v in rows)


def _attach_zip(evidence_package_name, declaration, payload):
    """把 ZIP 存进 Frappe File，挂在 Evidence Package 上，返回 file_url

    注意：必须在 Evidence Package insert 之后调用——
    File 的attached_to_name 依赖目标文档已存在。
    """
    fname = (
        f"evidence_{declaration.name}"
        f"_{declaration.total_declared_jpy:.0f}JPY.zip"
    )

    file_doc = frappe.get_doc(
        {
            "doctype": "File",
            "file_name": fname,
            "content": payload,
            "attached_to_doctype": "Evidence Package",
            "attached_to_name": evidence_package_name,
            "is_private": 1,
        }
    )
    file_doc.flags.ignore_permissions = True
    file_doc.insert(ignore_permissions=True)

    return file_doc.file_url