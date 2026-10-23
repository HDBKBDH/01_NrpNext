"""标签文本生成（Brother P710BT / 24mm 标签）

两类标签：
- 文字标签：型号全称 + SN，Tab 分隔，可直接粘贴到 P-touch Template
- 二维码标签：SN 生成二维码图片，供扫码入库

注意：ERPNext v16 中 `Serial Number` 已更名为 `Serial No`，
且 autoname = "field:serial_no"（name 取 serial_no 字段值）。
"""

import base64
import io

import frappe

COMPONENT_TYPES = ["CPU", "MEM", "GPU", "MB", "NVME", "PSU", "CHS"]


def generate_serial_number(dn_name, component_type, seq):
    """生成零件 SN

    dn_name: 拆解单名，如 261003-01
    component_type: CPU / MEM / GPU / MB / NVME / PSU / CHS
    seq: 同单同类型序号，从 1 开始

    返回：261003-01-CPU-01
    """
    return f"{dn_name}-{component_type}-{seq:02d}"


def build_label_payload(serial_numbers, remark=None):
    """生成文字标签的 Tab 分隔文本

    返回 TSV，每行一条：
        型号全称<TAB>SN[<TAB>备注]

    serial_numbers: str 或 list[str]
    """
    if isinstance(serial_numbers, str):
        serial_numbers = [serial_numbers]
    if not serial_numbers:
        return ""

    # v16：Serial No 的主键字段是 serial_no
    # 注意：v16 的 get_all / get_list 不再接受 as_dict 参数。
    # 需要 dict 就用 frappe.db.get_value(..., as_dict=True)，
    # 或者 frappe.get_all 返回的本来就是 dict 列表（默认行为）。
    rows = frappe.get_all(
        "Serial No",
        filters={"serial_no": ["in", serial_numbers]},
        fields=["serial_no", "item_code"],
    )
    if not rows:
        return ""

    item_codes = [r.get("item_code") for r in rows if r.get("item_code")]
    item_map = {}
    if item_codes:
        for it in frappe.get_all(
            "Item",
            filters={"name": ["in", item_codes]},
            fields=["name", "item_name"],
        ):
            item_map[it["name"]] = it["item_name"]

    sn_map = {r.get("serial_no"): r.get("item_code") for r in rows}

    lines = []
    for sn in serial_numbers:
        cols = [item_map.get(sn_map.get(sn, ""), ""), sn]
        if remark:
            cols.append(remark.strip())
        lines.append("\t".join(cols))

    return "\n".join(lines)


def _make_qr(serial_number, box_size=6, border=2):
    """构造 QRCode 对象（校验 qrcode 依赖是否可用）"""
    try:
        import qrcode
    except ImportError:
        frappe.throw(
            frappe._(
                "缺少 qrcode 库。执行：bench --site <site> install-app j2c_istk"
            ),
            title=frappe._("二维码依赖缺失"),
        )

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(serial_number)
    qr.make(fit=True)
    return qr


def generate_qr_png(serial_number, box_size=6, border=2):
    """生成 SN 二维码 PNG，返回 bytes

    用于存成 Frappe File（Attach 字段）。

    不要用 Data URI 存 Attach Image 字段——
    Frappe 的 Attach Image 组件会请求 /files/<value>，
    拿到的是一串 base64 字符串，必然 404 图片显示不出来。
    """
    img = _make_qr(serial_number, box_size, border).make_image(
        fill_color="black", back_color="white"
    )
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def generate_qr_data_uri(serial_number, box_size=6, border=2):
    """生成 SN 二维码的 Data URI

    返回 "data:image/png;base64,xxxx"。
    仅用于需要内联 base64 的场景（如 PDF 嵌入），
    存 Frappe Attach 字段请用 generate_qr_png。
    """
    img = _make_qr(serial_number, box_size, border).make_image(
        fill_color="black", back_color="white"
    )
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}"
