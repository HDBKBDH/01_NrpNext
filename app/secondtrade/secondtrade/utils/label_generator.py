"""标签文本生成（Brother P710BT / 24mm 标签）

两类标签：
- 文字标签：型号全称 + SN，Tab 分隔，可直接粘贴到 P-touch Template
- 二维码标签：SN 生成二维码图片，供扫码入库

注意：ERPNext v16 中 `Serial Number` 已更名为 `Serial No`，
且 autoname = "field:serial_no"（name 取 serial_no 字段值）。
"""

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


def generate_text_labels(serial_numbers):
    """生成文字标签文本（TSV，Tab 分隔）

    输出格式（可直接导入 Brother P-touch Template）：
        型号<TAB>序列号
        Corsair VENGERNCE DDR4-3200 32G(16G*2)<TAB>261003-01-MEM-01
    """
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
        # 退回：Serial No 尚未生成时，从拆解单子表读
        dn_rows = frappe.get_all(
            "Disassembly Note Item",
            filters={"serial_number": ["in", serial_numbers]},
            fields=["serial_number", "item"],
            as_dict=True,
        )
        rows = [
            {"serial_no": r["serial_number"], "item_code": r["item"]}
            for r in dn_rows
        ]

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

    lines = ["型号\t序列号"]
    for sn in serial_numbers:
        item_name = item_map.get(sn_to_item.get(sn, ""), "")
        lines.append(f"{item_name}\t{sn}")

    return "\n".join(lines)


def generate_qr_image(serial_number):
    """生成 SN 二维码图片（Data URI）"""
    import base64
    import io

    try:
        import qrcode
    except ImportError:
        frappe.throw(_("需要安装 qrcode 库：pip install qrcode"))

    img = qrcode.make(serial_number)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}"