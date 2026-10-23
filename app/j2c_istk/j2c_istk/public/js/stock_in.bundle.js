// 入库单 —— 前端交互
//   1. 选仓库 → 自动带出公司（只读）
//   2. 子表每行：采购价+ 运费 - 折扣 → × 当日汇率 = 采购合计
//   3. 单位「对」→ 该行最多 2 个编号；其他单位 1 行
//   4. 编号 → 带出历史同编号的厂商/型号/规格
//
// 注意：Frappe v16 已移除 frm.dashboard.show_dependent_label，
//      所有 docfields 访问都必须做空值保护。

frappe.ui.form.on("Stock In", {
    onload(frm) {
        // Section 1 的 5 个字段同一行是 Frappe 原生行为：
        // scss/desk/form.scss:623  .form-column.col-sm-20 { flex: 0 0 20% }
        // 每列 20%，一行正好 5 个。无需干预，勿覆盖 col-sm-20。
        setTimeout(() => hide_link_open_button(), 500);
    },

    refresh(frm) {
        if (typeof frm.is_new === "function" && frm.is_new()) {
            if (!(frm.doc.serial_numbers || []).length) {
                // 新单据初始化：保证至少有一行（用户要求最少保留一行）。
                // show=false —— 不自动展开编辑表单。
                const grid = frm.fields_dict.serial_numbers &&
                             frm.fields_dict.serial_numbers.grid;
                if (grid) {
                    grid.add_new_row(null, null, false, null, false);
                } else {
                    frm.add_row("serial_numbers");
                }
            }
            // 新单据：读 DocField 的 default（JP），填仓库以触发联动带出公司
            const whDf = (frm.docfields || []).find((d) => d.fieldname === "warehouse");
            if (!frm.doc.warehouse && whDf && whDf.default) {
                frm.set_value("warehouse", whDf.default);
            }
        }
        setTimeout(() => {
            hide_link_open_button();
            hide_name_column(frm);
            setup_row_actions(frm);
            stretch_grid(frm);
        }, 400);
    },

    // ---- 子表变化 → 重绘行操作图标 ----
    serial_numbers(frm) {
        setTimeout(() => {
            hide_name_column(frm);
            setup_row_actions(frm);
        }, 120);
    },

    // ---- 单位在主表：切「对」→ 2 行；其他 → 1 行 ----
    uom(frm) {
        const rows = frm.doc.serial_numbers || [];
        if (frm.doc.uom === "对") {
            while (frm.doc.serial_numbers.length < 2) {
                const grid = frm.fields_dict.serial_numbers &&
                             frm.fields_dict.serial_numbers.grid;
                if (grid) grid.add_new_row(null, null, false, null, false);
                else frm.add_row("serial_numbers");
            }
        } else if (rows.length > 1) {
            frm.doc.serial_numbers = [rows[0]];
            frm.refresh_field("serial_numbers");
        }
    },

    // ---- 选仓库 → 自动带出并锁定公司 ----
    warehouse(frm) {
        if (!frm.doc.warehouse) return;

        frappe.db.get_value("Warehouse", frm.doc.warehouse, "company", (r) => {
            const wh_company = r.message ? r.message.company : "";
            // __syncing 防止 warehouse↔company 双向联动互相触发
            frm.doc.__syncing = true;
            frm.set_value("company", wh_company);
            delete frm.doc.__syncing;

            // 公司锁定由 DocField.read_only_depends_on = "eval:doc.warehouse"
            // 原生实现（仓库有值 → 公司只读），不靠 DOM hack ——
            // DOM 级 readOnly 会被 Frappe 每次 refresh_field 重绘抹掉。
            hide_link_open_button();
        });
    },

});

frappe.ui.form.on("Stock In Item", {
    // 任一列变化 → 重算本行的采购合计和盈亏
    purchase_price_jpy: recalc_child,
    shipping_jpy: recalc_child,
    discount: recalc_child,
    market_price_cny: recalc_child,
    exchange_rate: recalc_child,


    // 编号变化 → 带出历史同编号的零件类型/厂商/型号/规格供参考
    serial_no(frm, cdt, cdn) {
        if (!cdn || !cdn.serial_no) return;

        frappe.db
            .get_value("Stock In Item", { serial_no: cdn.serial_no }, ["parent"])
            .then((r) => {
                if (!r || !r.message || !r.message.parent) return;
                return frappe.db
                    .get_value(
                        "Stock In",
                        r.message.parent,
                        ["manufacturer", "model", "specification"]
                    )
                    .then((doc) => {
                        if (!doc || !doc.message) return;
                        // 这三个字段在主表（整单一份）
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

/** 子表触发器统一入口 */
function recalc_child(frm, cdt, cdn) {
    const idx = (frm.doc.serial_numbers || []).findIndex((r) => r.name === cdn.name);
    if (idx >= 0) recalc_row(frm, "serial_numbers", idx);
}

/** 本行金额重算。

   采购合计 =（采购价 + 运费 - 折扣）× 购买汇率
   盈亏     =（行情价 - 采购合计）× 数量
*/
function recalc_row(frm, dt, idx) {
    const row = frm.doc[dt][idx];

    // 小计¥ (JPY) = 采购价 + 运费 - 折扣
    const jpy = flt(row.purchase_price_jpy) + flt(row.shipping_jpy) - flt(row.discount);
    if (flt(row.total_jpy) !== jpy) {
        frm.set_value("total_jpy", jpy, dt, row.name);
    }

    // 成本¥ (CNY) = 小计¥ × 购买汇率（汇率在行内，可逐行不同）
    const rate = flt(row.exchange_rate);
    const total = jpy && rate ? flt(jpy * rate, 2) : 0;
    if (flt(row.total_cny) !== total) {
        frm.set_value("total_cny", total, dt, row.name);
    }

    // 盈亏 =（行情价 - 成本¥）× 数量（数量在主表，整单一份）
    const qty = flt(frm.doc.qty) || 1;
    const profit = row.market_price_cny
        ? flt((flt(row.market_price_cny) - total) * qty, 2)
        : 0;
    if (flt(row.profit_cny) !== profit) {
        frm.set_value("profit_cny", profit, dt, row.name);
    }

    // 只读字段（合计/盈亏）即使为 0 也要显示 0，不能显示 placeholder。
    // Frappe 对 read_only 字段：值为空/0 时会显示 placeholder。
    ["total_jpy", "total_cny", "profit_cny"].forEach((f) => {
        if (row[f] === undefined || row[f] === null) {
            frm.set_value(f, 0, dt, row.name);
        }
    });
}

/** 隐藏 warehouse 字段的 🔗 跳转按钮（v16 的 class 是 .btn-open） */
function hide_link_open_button() {
    try {
        document.querySelectorAll(".btn-open").forEach((b) => {
            const wrap = b.closest('[data-fieldname]');
            if (wrap && wrap.getAttribute("data-fieldname") === "warehouse") {
                b.style.display = "none";
            }
        });
    } catch (e) {
        /* DOM 还没就绪 */
    }
}
/** 子表行操作：把 Frappe 的「添加行 / 删除行」按钮移到每行末尾。

   Frappe v16 默认：
     - 表格下方有「添加行」按钮（.grid-add-row）
     - 勾选行后表格下方出现「删除行」按钮（.grid-remove-rows）

   需求：改为每行末尾一列图标 —— ＋ 加一行、－ 删当前行，最少保留一行。
   实现：隐藏原生按钮，在每行末尾插入图标列，onclick 调 grid API。

   注意：不能用 DOM hack 对抗 refresh（会被重绘抹掉），
   所以用 after_render 事件重新绑定 —— grid 每次重绘都会触发。
*/
// 注意：子表行操作图标挂在上面那个 frappe.ui.form.on("Stock In") 里的
// serial_numbers 触发器（见 refresh 定义处），不要在这里重复注册
// —— Frappe 的 form.on 是覆盖式，同名 doctype 只会保留最后一次注册。

/** 强制子表撑满整行。

   Frappe 把字段包在 .form-column（Bootstrap 栅格 flex:0 0 20%），
   Table 字段在同列里会被限制到 20% 宽。CSS 用 :has() 匹配，
   但为保险这里用 JS 直接改样式。
*/
function stretch_grid(frm) {
    try {
        // 子表所在列撑满
        const el = document.querySelector(
            '.form-layout .frappe-control[data-fieldname="serial_numbers"]'
        );
        if (el) {
            // 只撑满「含子表的那个 Section」，不改其他 Section 的 Column 宽度
            const section = el.closest(".form-section");
            if (section) {
                section.style.maxWidth = "100%";
                const col = el.closest(".form-column");
                if (col) {
                    col.style.flex = "1 1 100%";
                    col.style.width = "100%";
                    col.style.maxWidth = "100%";
                }
            }
            el.style.flex = "1 1 100%";
            el.style.width = "100%";
            el.style.maxWidth = "100%";
        }

    } catch (e) {
        /* DOM 未就绪 */
    }
}

/** 隐藏 Frappe 自动生成的「编号 / name」列。

   子表 DocType 的主键（name / idx）Frappe 会自动渲染成第一列，
   label 取 DocType 名（这里是「编号」）。业务上不需要，隐藏掉。

   注意：必须用 .grid-row .grid-static-col[data-fieldname="name"] 精确匹配，
   不能靠位置猜。
*/
function hide_name_column(frm) {
    try {
        const grid = frm.fields_dict.serial_numbers &&
                     frm.fields_dict.serial_numbers.grid;
        if (!grid || !grid.wrapper || !grid.wrapper.length) return;
        grid.wrapper
            .find('.grid-row .grid-static-col[data-fieldname="name"], .grid-heading-row [data-fieldname="name"]')
            .addClass("hidden");
    } catch (e) {
        /* grid 未就绪 */
    }
}

/** 在每行行首插入 ＋/－ 图标。

   Frappe v16 的 grid 行结构（实测）：
       <div class="grid-row">
           <div class="data-row row m-0">   ← 真正的行容器，所有列在里面
               <div class="grid-static-col" data-fieldname="..."> ...
           </div>
       </div>

   要点：
     - 行容器是 .data-row，不是 .grid-row，也不是 .grid-static-col
     - 图标容器必须是一个完整的 <div>，用 jQuery 对象创建，
       不要用字符串拼接（之前闭合标签写错，导致图标变成兄弟节点）
*/
function setup_row_actions(frm) {
    try {
        const grid = frm.fields_dict.serial_numbers &&
                     frm.fields_dict.serial_numbers.grid;
        if (!grid || !grid.wrapper || !grid.wrapper.length) return;
        const wrapper = grid.wrapper;

        // 隐藏原生「添加行 / 删除行」文字按钮
        wrapper.find(".grid-add-row").addClass("hidden");
        wrapper.find(".grid-remove-rows").addClass("hidden");

        // 表头补一个同宽空列，否则表头与数据列会错位
        const $headRow = wrapper.find(".grid-row").filter(function () {
            return !$(this).data("idx") || $(this).data("idx") === "0";
        }).first();
        if ($headRow.length && !$headRow.find(".row-actions").length) {
            const $headData = $headRow.find(".data-row").first();
            if ($headData.length) {
                const $headActs = $("<div>", { class: "row-actions" });
                const $headFirst = $headData.children(".grid-static-col").first();
                if ($headFirst.length) $headFirst.before($headActs);
                else $headData.prepend($headActs);
            }
        }

        wrapper.find(".grid-row").each(function () {
            const $gridRow = $(this);
            if (!$gridRow.data("idx") || $gridRow.data("idx") === "0") return; // 表头

            const $dataRow = $gridRow.find(".data-row").first();
            if (!$dataRow.length) return;
            if ($dataRow.find(".row-actions").length) return;   // 已加过

            // 用 $("<div>") 创建，保证结构正确
            const $acts = $("<div>", { class: "row-actions" });
            const $add = $("<a>", { class: "row-act-add", title: "添加一行" })
                .html(frappe.utils.icon("plus", "xs"));
            const $del = $("<a>", { class: "row-act-del", title: "删除本行" })
                .html(frappe.utils.icon("minus", "xs"));
            $acts.append($add).append($del);

            // 插到第一列（商品编号）之前 —— 也就是行号列（「编号」）
            // 正右侧，形成独立一格。
            const $firstCol = $dataRow.children(".grid-static-col").first();
            if ($firstCol.length) {
                $firstCol.before($acts);
            } else {
                $dataRow.prepend($acts);
            }

            $add.on("click", (e) => {
                e.preventDefault();
                // 在当前行下方插入一个空白行，不自动展开编辑表单。
                // add_new_row(idx, callback, show, copy_doc, go_to_last_page)
                //   show=true 是 Frappe 默认行为（会弹出编辑表单），
                //   这里传 false —— 用户要求 ＋ 只加行，
                //   需要填数据时点该行右侧的铅笔图标展开。
                const idx = parseInt($gridRow.data("idx"), 10);
                grid.add_new_row(
                    Number.isNaN(idx) ? null : idx,
                    null,
                    false,
                    null,
                    false
                );
            });
            $del.on("click", (e) => {
                e.preventDefault();
                // 最少保留一行
                if ((frm.doc.serial_numbers || []).length <= 1) return;

                // Frappe v16 没有 remove_row()，删除逻辑在 delete_rows() 里：
                //   this.grid_rows_by_docname[doc.name]?.remove();
                const dn = $gridRow.data("name");
                if (!dn) return;

                // 先更新 doc 里的行数组，再移除 DOM 行，最后整体刷新
                // ——顺序错了会导致 Frappe 用旧数据重绘。
                const i = (frm.doc.serial_numbers || []).findIndex((r) => r.name === dn);
                if (i < 0) return;
                frm.doc.serial_numbers.splice(i, 1);

                const row = grid.grid_rows_by_docname[dn];
                if (row && typeof row.remove === "function") {
                    row.remove();
                }

                // 整体刷新 —— 触发 grid.refresh hook，重挂所有行的图标
                grid.refresh();
                frm.refresh_field("serial_numbers");
            });
        });

        // 行数变化后重绘图标。
        // 不能用 DOMSubtreeModified —— Frappe grid 用虚拟 DOM 增量更新，
        // 不产生该事件（旧行会一直没有图标）。
        // 正确做法：hook grid.refresh()，每次重绘后重新挂图标。
        if (!grid.__row_actions_hooked) {
            grid.__row_actions_hooked = true;
            const origRefresh = grid.refresh.bind(grid);
            grid.refresh = function (...args) {
                const r = origRefresh(...args);
                setTimeout(() => setup_row_actions(frm), 80);
                return r;
            };
        }
    } catch (e) {
        /* grid 未就绪 */
    }
}
