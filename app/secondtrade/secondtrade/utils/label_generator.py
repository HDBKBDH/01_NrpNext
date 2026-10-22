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
    rows = frappe.get_all(
        "Serial No",
        filters={"serial_no": ["in", serial_numbers]},
        fields=["serial_no", "item_code"],
        as_dict=True,
    )
    if not rows:
        return ""

    item_codes = [r["item_code"] for r in rows if r["item_code"]]
    item_map = {}
    if item_codes:
        for it in frappe.get_all(
            "Item",
            filters={"name": ["in", item_codes]},
            fields=["name", "item_name"],
        ):
            item_map[it["name"]] = it["item_name"]

    sn_to_item = {r["serial_no"]: r["item_code"] for r in rows}

    lines = []
    for sn in serial_numbers:
        cols = [item_map.get(sn_to_item.get(sn, ""), ""), sn]
        if remark:
            cols.append(remark.strip())
        lines.append("\t".join(cols))

    return "\n".join(lines)


def generate_qr_data_uri(serial_number, box_size=6, border=2):
    """生成 SN 二维码的 Data URI

    返回 "data:image/png;base64,xxxx"，可直接存进 Attach Image 字段。
    """
    try:
        import qrcode
    except ImportError:
        frappe.throw(
            frappe._(
                "缺少 qrcode 库。执行：bench --site <site> install-app secondtrade"
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

    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}"