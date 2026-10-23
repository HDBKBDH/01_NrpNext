"""成本分摊算法

设计要点：
- 原始成本永久锁定（purchase_cost）
- 退税调整可追加（tax_refund_adjustment）
- 分摊权重 = 采购时参考价（market_ref_price_cny）
- 物流批次成本同样按参考价权重分摊
"""

import frappe
from frappe import _


def allocate_by_reference_price(items, total_cost):
    """按采购时参考价权重分摊总成本到items

    items: [{'market_ref_price_cny': float, '_target': obj}]
    total_cost: 需要分摊的总金额

    返回分摊系数；items 内的 target 对象会被写入分摊结果
    """
    total_ref = sum(
        frappe.utils.flt(i.get("market_ref_price_cny")) for i in items
    )
    if total_ref <= 0:
        frappe.throw(_("参考价总和不能为 0，无法分摊成本"))

    ratio = frappe.utils.flt(total_cost) / total_ref

    for i in items:
        ref = frappe.utils.flt(i.get("market_ref_price_cny"))
        allocated = round(ref * ratio, 2)
        i["allocated_cost"] = allocated

        # 写回 target。
        # 注意：不要用 hasattr(target, "allocated_cost") 做前置判断——
        # 适配器类（_AllocTarget）用 __setattr__ 转发写入，
        # 实例上并没有 allocated_cost 这个属性，hasattr 会返回 False，
        # 结果整段写入被静默跳过（分摊永远是 0）。
        target = i.get("_target")
        if target is not None:
            setattr(target, "allocated_cost", allocated)

    return ratio


def calculate_final_cost(item):
    """计算零件最终成本

    final_cost = 分摊采购成本 + 分摊物流成本 + 退税调整
    """
    return round(
        frappe.utils.flt(item.allocated_purchase_cost)
        + frappe.utils.flt(item.allocated_logistics_cost)
        + frappe.utils.flt(item.tax_refund_adjustment),
        2,
    )


def calculate_capital_cost(item_cost, purchase_date, as_of_date=None, annual_rate=None):
    """资金占用成本

    capital_cost = 库存成本 × 年化资金成本率 × 持有天数 / 365
    """
    if annual_rate is None:
        annual_rate = frappe.db.get_single_value("Trade Settings", "capital_cost_rate")
    annual_rate = frappe.utils.flt(annual_rate) / 100

    if not as_of_date:
        as_of_date = frappe.utils.today()

    holding_days = (
        frappe.utils.getdate(as_of_date) - frappe.utils.getdate(purchase_date)
    ).days

    if holding_days <= 0:
        return 0.0

    return round(
        frappe.utils.flt(item_cost) * annual_rate * (holding_days / 365), 2
    )
