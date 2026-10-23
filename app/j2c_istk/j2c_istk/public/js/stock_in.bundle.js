// 入库单 —— 前端交互
//   1. 选仓库 → 自动带出公司（只读）
//   2. 采购价/运费/折扣/汇率 → 自动算 CNY
//   3. 单位切「对」→ 自动补到 2 行；切回「单个/台」→ 只留 1 行
//   4. 商品编号输入框 → 提示最近录入过的编号
//   5. 选已有编号 → 自动带出厂商/型号/规格

frappe.ui.form.on("Stock In", {
    refresh(frm) {
        if (frm.is_new()) {
            frm.set_value("qty", 1);
            frm.set_value("uom", "单个");
            if (!(frm.doc.serial_numbers || []).length) {
                frm.add_row("serial_numbers");
            }
        }
    },

    // ---- 仓库 → 公司 ----
    warehouse(frm) {
        if (!frm.doc.warehouse) {
            frm.set_value("company", "");
            return;
        }
        frappe.db.get_value("Warehouse", frm.doc.warehouse, "company", (r) => {
            frm.set_value("company", r.message ? r.message.company : "");
        });
    },

    // ---- 金额自动计算 ----
    purchase_price_jpy: recalc_cny,
    shipping_jpy: recalc_cny,
    discount: recalc_cny,
    exchange_rate: recalc_cny,

    // ---- 单位 → 行数 ----
    uom(frm) {
        const rows = frm.doc.serial_numbers || [];
        if (frm.doc.uom === "对") {
            for (let i = rows.length; i < 2; i++) frm.add_row("serial_numbers");
        } else if (rows.length > 1) {
            frm.doc.serial_numbers = [rows[0]];
            frm.refresh_field("serial_numbers");
        }
    }
});

/** CNY = (采购价 + 运费 - 折扣) × 汇率 */
function recalc_cny(frm) {
    const jpy = flt(frm.doc.purchase_price_jpy) + flt(frm.doc.shipping_jpy) - flt(frm.doc.discount);
    const rate = flt(frm.doc.exchange_rate);
    frm.set_value("total_cny", jpy && rate ? flt(jpy * rate, 2) : 0);
}

// ---- 子表：商品编号 ----
frappe.ui.form.on("Stock In Item", {
    serial_no: function (frm, cdt, cdn) {
        if (!cdn.serial_no) return;

        // 若该编号已有历史入库记录，带出厂商/型号/规格供参考
        frappe.db
            .get_value("Stock In Item", { serial_no: cdn.serial_no },
                ["parent", "name"])
            .then((r) => {
                if (!r || !r.message || !r.message.parent) return;
                return frappe.db
                    .get_value("Stock In", r.message.parent,
                        ["manufacturer", "model", "specification"])
                    .then((doc) => {
                        if (!doc || !doc.message) return;
                        for (const f of ["manufacturer", "model", "specification"]) {
                            if (!frm.doc[f] && doc.message[f]) {
                                frm.set_value(f, doc.message[f]);
                            }
                        }
                    });
            })
            .catch(() => {});
    }
});

/**
 * 商品编号输入框：显示最近录入过的编号作为提示。
 * 用 Link 风格的过滤查询，实现在点击输入框时弹出最近 10 条。
 */
function setup_serial_lookup(frm) {
    const dfa = frm.docfields.find(
        (d) => d.fieldname === "serial_numbers" && d.reqd
    );
    if (!dfa) return;

    // 在子表编辑器里给 serial_no 列加 query
    const grid = dfa.grid;
    if (!grid || grid.docfields.__lookup_installed) return;
    grid.docfields.__lookup_installed = true;

    const df = grid.docfields.find((d) => d.fieldname === "serial_no");
    if (!df) return;

    df.get_query = function () {
        return {
            query: "j2c_istk.j2c_istk.doctype.stock_in.stock_in.get_recent_serials",
        };
    };
    frm.refresh_field("serial_numbers");
}