// 入库单 —— 前端交互
//   1. 选仓库 → 自动带出公司（只读）
//   2. 采购价/运费/折扣/汇率 → 自动算 CNY
//   3. 单位切「对」→ 自动补到 2 行；切回「单个/台」→ 只留 1 行
//   4. 商品编号输入框 → 提示最近录入过的编号
//   5. 选已有编号 → 自动带出厂商/型号/规格

frappe.ui.form.on("Stock In", {
    onload(frm) {
        // 隐藏 Link 的「打开链接」按钮（🔗）。
        // 用 querySelector 直接查 DOM，不碰 frm.docfields ——
        // onload 时它可能还没渲染，访问会抛 undefined.find。
        setTimeout(() => hide_link_open_button(), 400);
    },

    refresh(frm) {
        if (typeof frm.is_new === "function" && frm.is_new()) {
            frm.set_value("qty", 1);
            frm.set_value("uom", "单个");
            if (!(frm.doc.serial_numbers || []).length) {
                frm.add_row("serial_numbers");
            }
        }
        setTimeout(() => hide_link_open_button(), 400);
    },

    // ---- 仓库 → 公司 ----
    warehouse(frm) {
        if (!frm.doc.warehouse) {
            frm.set_value("company", "");
            return;
        }
        frappe.db.get_value("Warehouse", frm.doc.warehouse, "company", (r) => {
            frm.set_value("company", r.message ? r.message.company : "");
            // Frappe 会给「空值 + read_only」的字段加 hide-control 导致不可见，
            // 带出公司值后必须显式显示。
            // v16 只有 refresh_field / toggle_display，没有 show_dependent_label。
            frm.refresh_field("company");
            frm.toggle_display("company", true);
            hide_link_open_button();
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

/** 隐藏 Link 字段的 🔗 跳转按钮（v16 的 class 是 .btn-open） */
function hide_link_open_button() {
    try {
        document.querySelectorAll(".btn-open").forEach((b) => {
            // 只隐藏 warehouse 字段里的，别误伤其他 Link
            const wrap = b.closest('[data-fieldname]');
            if (wrap && wrap.getAttribute("data-fieldname") === "warehouse") {
                b.style.display = "none";
            }
        });
    } catch (e) {
        /* DOM 还没就绪 */
    }
}

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
