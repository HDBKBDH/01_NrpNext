// Customs Declaration 前端脚本
//
// 设计要点（按冰的要求）：
//   整机拆件和散件统一入口，操作上没区别。
//   明细行显示源单号（261003-01 / LPP-00001）便于追溯。
//   金额只显示日元，人民币是内部记账不显示。

frappe.ui.form.on("Customs Declaration", {
	refresh(frm) {
		if (frm.is_new()) {
			frm.add_custom_button(__("从拆解单抓取零件"), () =>
				pick_source(frm, "Disassembly")
			);
			frm.add_custom_button(__("从散件采购单抓取"), () =>
				pick_source(frm, "LoosePurchase")
			);
		}

		// 人民币字段隐藏（内部记账用）
		render_jpy_only(frm);
	},

	// 汇率变化时重算人民币记账值
	exchange_rate(frm) {
		refresh_cny(frm);
	},
});

/**
 * 选来源单并抓取商品
 */
function pick_source(frm, type) {
	const is_dn = type === "Disassembly";

	const dialog = new frappe.ui.Dialog({
		title: is_dn ? __("从拆解单抓取零件") : __("从散件采购单抓取"),
		fields: [
			{
				fieldname: "source",
				fieldtype: "Link",
				label: is_dn ? __("拆解单") : __("散件采购单"),
				options: is_dn ? "Disassembly Note" : "Loose Part Purchase",
				reqd: 1,
			},
			{
				fieldname: "info",
				fieldtype: "HTML",
				label: __("说明"),
			},
		],
		primary_action_label: __("抓取"),
		primary_action(values) {
			const method = is_dn
				? "get_parts_from_disassembly"
				: "get_parts_from_purchase";

			frappe.call({
				method: "j2c_istk.j2c_istk.doctype.customs_declaration.customs_declaration."
					+ method,
				args: {
					disassembly_note: is_dn ? values.source : undefined,
					loose_part_purchase: is_dn ? undefined : values.source,
				},
				callback(r) {
					const msg = __("已添加 {0} 条，跳过 {1} 条，当前共 {2} 条", [
						r.message.added,
						r.message.skipped,
						r.message.total,
					]);
					frappe.msgprint({
						message: msg,
						indicator: r.message.added ? "green" : "orange",
					});
					dialog.hide();
					frm.refresh();
				},
				error() {
					dialog.hide();
				},
			});
		},
	});

	dialog.show();
}

/**
 * 明细里只显示日元，人民币列隐藏
 */
function render_jpy_only(frm) {
	const f = frm.get_field("items");
	if (!f || !f.grid) return;

	const cny_fields = new Set([
		"declared_price_cny",
		"declared_amount_cny",
		"actual_cost_cny",
	]);

	// Frappe 会按 DocField.hidden 隐藏，这里额外兜底
	setTimeout(() => {
		f.grid.docfields.forEach((df) => {
			if (cny_fields.has(df.fieldname)) {
				df.hidden = 1;
				df.depends_on = "0";
			}
		});
		f.grid.refresh();
	}, 300);
}

/**
 * 汇率变化后重算人民币（隐藏字段，仅数据正确）
 */
function refresh_cny(frm) {
	// 服务端 validate 会重算，这里不需要额外处理
	return;
}