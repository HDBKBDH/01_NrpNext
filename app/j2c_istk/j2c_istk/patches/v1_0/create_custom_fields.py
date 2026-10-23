"""创建所有 Custom Field"""

import frappe

ITEMS = [
    dict(fieldname="model_series", fieldtype="Data", label="规格/系列",
         insert_after="item_name", translatable=True),
    dict(fieldname="model_number", fieldtype="Data", label="型号",
         insert_after="model_series"),
    dict(fieldname="capacity", fieldtype="Data", label="容量",
         insert_after="model_number"),
    dict(fieldname="frequency", fieldtype="Data", label="频率",
         insert_after="capacity"),
    dict(fieldname="is_second_hand", fieldtype="Check", label="二手商品",
         insert_after="item_defaults", default="1"),
    dict(fieldname="condition_grade", fieldtype="Select", label="成色",
         options="Excellent\nGood\nFair\nDefective\nForParts\nUnknown",
         insert_after="is_second_hand"),
    dict(fieldname="defect_note", fieldtype="Text", label="瑕疵描述",
         insert_after="condition_grade"),
    dict(fieldname="stock_category", fieldtype="Select", label="库存状态",
         options="InTransit\nSellable\nSelfUse", insert_after="defect_note"),
]

PURCHASE_RECEIPT = [
    dict(fieldname="st_jpy_original", fieldtype="Currency",
         label="日元原价 (JPY)", options="JPY", insert_after="grand_total"),
    dict(fieldname="st_settlement_rate", fieldtype="Float",
         label="结算汇率", insert_after="st_jpy_original"),
    dict(fieldname="st_cny_cost", fieldtype="Currency",
         label="实际 CNY 成本", options="CNY", insert_after="st_settlement_rate"),
    dict(fieldname="st_tax_refund_status", fieldtype="Select",
         label="退税状态",
         options="Completed\nPendingProof\nUndetermined\nPersonalSeller",
         insert_after="st_cny_cost"),
    dict(fieldname="st_payment_method", fieldtype="Select",
         label="支付方式",
         options="WeChat\nAlipay\nChinaCard\nJapanCard\nPayPayBalance\n"
                 "PayPayCard\nPayPayBank\nRakutenCard\nJapanPostBank\n"
                 "CompanyTransfer\nPersonalTransfer\nCash",
         insert_after="st_tax_refund_status"),
    dict(fieldname="st_supplier_type", fieldtype="Select", label="卖家类型",
         options="Company\nIndividual\nTourist", insert_after="st_payment_method"),
    dict(fieldname="st_purchase_platform", fieldtype="Data", label="采购平台",
         insert_after="st_supplier_type"),
    dict(fieldname="st_local_shipping_jpy", fieldtype="Currency",
         label="日本境内运费 (JPY)", options="JPY",
         insert_after="st_purchase_platform"),
]

SALES_INVOICE = [
    dict(fieldname="st_sales_channel", fieldtype="Link", label="销售渠道",
         options="Warehouse", insert_after="company"),
    dict(fieldname="st_xianyu_order_no", fieldtype="Data", label="闲鱼订单号",
         insert_after="st_sales_channel"),
    dict(fieldname="st_sale_date", fieldtype="Date", label="销售日期",
         insert_after="st_xianyu_order_no"),
]

WAREHOUSE = [
    dict(fieldname="st_warehouse_type", fieldtype="Select", label="仓库类型",
         options="Group\n物流仓\n中转仓\n销售仓\n自用仓\n虚拟仓",
         insert_after="warehouse_type"),
    dict(fieldname="st_country", fieldtype="Link", label="国家/地区",
         options="Country", insert_after="st_warehouse_type"),
    dict(fieldname="st_is_selfuse", fieldtype="Check", label="公司留用",
         insert_after="st_country"),
    dict(fieldname="st_is_virtual", fieldtype="Check", label="虚拟仓",
         insert_after="st_is_selfuse"),
    dict(fieldname="st_stock_state", fieldtype="Select", label="库存状态",
         options="InTransit\nSellable\nSelfUse", insert_after="st_is_virtual"),
    dict(fieldname="st_contact_person", fieldtype="Data", label="联系人",
         insert_after="st_stock_state"),
    dict(fieldname="st_contact_phone", fieldtype="Data", label="电话",
         insert_after="st_contact_person"),
    dict(fieldname="st_full_address", fieldtype="Small Text", label="完整地址",
         insert_after="st_contact_phone"),
]


def execute():
    for doctype, fields in [
        ("Item", ITEMS),
        ("Purchase Receipt", PURCHASE_RECEIPT),
        ("Sales Invoice", SALES_INVOICE),
        ("Warehouse", WAREHOUSE),
    ]:
        for f in fields:
            name = f"{doctype}-{f['fieldname']}"
            if frappe.db.exists("Custom Field", name):
                continue
            cf = frappe.get_doc(dict(doctype="Custom Field", dt=doctype, **f))
            cf.insert(ignore_permissions=True)
            print(f"  ✓ {doctype}.{f['fieldname']}")
