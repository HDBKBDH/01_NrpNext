import frappe
from frappe.model.document import Document


class MarketPriceHistory(Document):
    def validate(self):
        self.set_model_info()
        self.calculate_change()

    def set_model_info(self):
        if not self.model:
            return
        info = frappe.db.get_value(
            "Item",
            self.model,
            ["item_name", "item_group", "brand"],
            as_dict=True,
        )
        if info:
            self.model_name = info.item_name
            self.item_group = info.item_group
            self.brand = info.brand

    def calculate_change(self):
        """带出上次行情价，计算涨跌"""
        if not self.model or not self.price_date:
            return

        prev = frappe.db.sql(
            """
            SELECT market_price_cny
            FROM `tabMarket Price History`
            WHERE model = %s
              AND docstatus = 1
              AND price_date < %s
            ORDER BY price_date DESC
            LIMIT 1
            """,
            (self.model, self.price_date),
            as_dict=True,
        )

        if not prev:
            self.previous_price_cny = 0
            self.change_amount = 0
            self.change_pct = 0
            return

        prev_price = frappe.utils.flt(prev[0]["market_price_cny"])
        self.previous_price_cny = prev_price

        if prev_price > 0:
            self.change_amount = round(self.market_price_cny - prev_price, 2)
            self.change_pct = round(
                (self.market_price_cny - prev_price) / prev_price * 100, 2
            )
        else:
            self.change_amount = 0
            self.change_pct = 0

    @staticmethod
    def get_current_price(model):
        """取某型号当前行情价（最新一条已提交的记录）"""
        rows = frappe.db.sql(
            """
            SELECT market_price_cny, price_date
            FROM `tabMarket Price History`
            WHERE model = %s AND docstatus = 1
            ORDER BY price_date DESC, creation DESC
            LIMIT 1
            """,
            (model,),
            as_dict=True,
        )
        if not rows:
            return None
        return rows[0]

    @staticmethod
    def get_price_n_days_ago(model, days):
        """取 N 天前的行情价"""
        cutoff = frappe.utils.add_days(frappe.utils.today(), -days)
        rows = frappe.db.sql(
            """
            SELECT market_price_cny, price_date
            FROM `tabMarket Price History`
            WHERE model = %s AND docstatus = 1 AND price_date <= %s
            ORDER BY price_date DESC
            LIMIT 1
            """,
            (model, cutoff),
            as_dict=True,
        )
        return rows[0] if rows else None
