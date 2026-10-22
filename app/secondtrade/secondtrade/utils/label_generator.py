"""标签文本生成（Brother P710BT / 24mm 标签）

两类标签：
- 文字标签：型号全称 + SN，可复制粘贴到标签机软件
- 二维码标签：SN 生成二维码图片，供扫码入库
"""

import frappe


COMPONENT_TYPES = ["CPU", "MEM", "GPU", "MB", "NVME", "PSU", "CHS"]


def generate_serial_number(dn_name, component_type, seq):
    """生成零件 SN

    dn_name: 拆解单名，如 261003-01
    component_type: CPU / MEM / GPU / MB / NVME / PSU / CHS
    seq: 同单同类型序号，从 1 开始
    """
    return f"{dn_name}-{component_type}-{seq:02d}"


def generate_text_labels(serial_numbers):
    """生成文字标签文本（TSV，Tab 分隔）

    型号全称\tSN
    Corsair VENGERNCE DDR4-3200 32G(16G*2)\t261003-01-MEM-01
    """
    items = frappe.get_all(
        "Serial Number",
        filters={"name": ["in", serial_numbers]},
        fields=["name", "item_code"],
    )
    names = frappe.get_all(
        "Item",
        filters={"name": ["in", [i["item_code"] for i in items]]},
        fields=["name", "item_name"],
        as_dict=True,
    )
    item_map = {n["name"]: n["item_name"] for n in names}

    lines = ["型号\t序列号"]
    for sn in serial_numbers:
        row = next((i for i in items if i["name"] == sn), None)
        item_name = item_map.get(row["item_code"], "") if row else ""
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
