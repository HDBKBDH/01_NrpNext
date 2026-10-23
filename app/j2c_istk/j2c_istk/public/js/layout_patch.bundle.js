/* ============================================================================
 * Frappe v16 — Section 内字段「每行 N 个 / 不等宽分多行」布局补丁
 * ----------------------------------------------------------------------------
 * 目标：
 *   1) 让 Section 内字段按「每行 N 个」自由控制（默认 5 个一行）
 *   2) 支持「不等宽分多行」：例如 11 个字段 → 5/2/4 三行，
 *      第1行每列20%、第2行每列50%、第3行每列25%
 *
 * 原理（已核对 frappe v16 源码）：
 *   - frappe/public/scss/desk/form.scss:73-82
 *       .section-body { display:flex; flex-wrap:wrap; }
 *     → 只要每列的 flex-basis 之和超过 100% 就会自动换行。
 *   - frappe/public/js/frappe/form/column.js  resize_all_columns()
 *       colspan = cint(12 / columns);  if (columns == 5) colspan = 20;
 *     → Section 内所有列共用一个 colspan，这是限制的根源。
 *   - frappe/public/scss/desk/form.scss:614-627
 *       .form-column.col-sm-20 { flex: 0 0 20%; max-width: 20%; }
 *     → col-sm-20 是 Frappe 私有的第 13~20 号栅格类，flex 写法，
 *       能被 flex-wrap 正确换行；而 Bootstrap 的 col-sm-1..12 只有
 *       `width` + `float:left`，在 flex 容器里 float 被忽略、
 *       flex-basis:auto→width，13 列以上会算出 colspan=0（col-sm-0，无此类）。
 *
 * 补丁入口（关键）：
 *   frappe.ui.form.Layout 是全局（layout.js:5 `frappe.ui.form.Layout = class Layout`）
 *   但 Column / Section / Tab 都是 ES module 的 default export，
 *   **无法从 window 直接拿到**。因此不能覆盖 Column.prototype.resize_all_columns。
 *   → 可行入口：覆盖 frappe.ui.form.Layout.prototype.make_column()，
 *     在其中拿到 new Column(...) 产生的实例后，直接改它的 wrapper 的样式；
 *     或在 Layout.prototype.render() 之后统一按 section 重排。
 *
 * 依赖：仅用 jQuery + 原生 DOM，不依赖任何 Frappe 内部模块。
 * 安装位置：app 的 public/js/layout_patch.bundle.js，通过 hooks.py 的 app_include_js 引入。
 *           必须以 .bundle.js 结尾 —— app_include_js 的文件由 esbuild 打包，
 *           原始 .js 会被当成静态资源直接引用，浏览器因 MIME 拒绝执行。
 * ========================================================================== */

/* ---------------------------------------------------------------------------
 * 0. 配置区（可直接改）
 * ------------------------------------------------------------------------- */
const LAYOUT_CONFIG = {
	// 全局默认：每个 Section 一行放几个字段。5 = 20% 宽（Frappe 的 col-sm-20）。
	// 设为 0 表示"沿用 Frappe 原始行为"。
	//
	// 为什么需要这个补丁（Frappe v16.52.0）：
	//   column.js:41 resize_all_columns()
	//       colspan = cint(12 / columns); if (columns == 5) colspan = 20;
	//   → Section 内所有列共用一个 colspan，只有「恰好5个」时才是设计值。
	//     11 个字段 → col-sm-1 → Bootstrap 的 col-sm-1..12 只有 width+float，
	//     在 flex 容器里 float 被忽略、flex-basis:auto→width → 全挤 8.33% 一行。
	//   而 Frappe 的本意（form.scss:73-77）是「每列 20%，靠 flex-wrap 自动换行」。
	default_per_row: 5,

	// 需要精确指定每列宽度的 Section。
	// key = Section Break 的 fieldname；value = 每列的百分比数组（按列顺序）。
	// 例：{ "details_section": [20, 20, 20, 20, 20, 50, 50, 25, 25, 25, 25] }
	section_widths: {},

	// 需要精确指定「每行几个」的 Section。
	// key = Section Break 的 fieldname；value = 每行的列数数组。
	// 例：{ "details_section": [5, 2, 4] }  → 第1行5列、第2行2列、第3行4列
	//
	// j2c_istk / Stock In（入库单）信息区：
	//   第1行 厂商|类型|支付方式|数量|单位          5 列各 20%
	//   第2行 型号|规格                2 列各 50%
	//   第3行 入库时间|购买日期|到货时间|仓库        4 列各 25%
	section_rows: {
		sec_g0: [5, 2, 4],
	},

	// 要跳过的 Section（fieldname 数组），不改变其布局。
	// sec_grid = 子表所在 Section，需要 100% 宽（子表独占整行），
	// 不能被统一成 20%。
	skip_sections: ["sec_grid"],
};

/* ---------------------------------------------------------------------------
 * 1. 工具函数
 * ------------------------------------------------------------------------- */

/** 把 Section Break 的 df 归一化成可用的标识 key */
function section_key(section) {
	const df = section.df || {};
	// Section Break 的 fieldname 形如 "details_section"；
	// Frappe 自动生成的没有 fieldname（__section_N）。
	if (df.fieldname) return df.fieldname;
	// 回退：用 label
	if (df.label) return df.label;
	return null;
}

/** 从 section 的列里取出「可见列」的 DOM 元素 */
function get_columns(section) {
	if (!section || !section.body) return [];
	return Array.from(section.body.children(".form-column"));
}

/**
 * 把一组百分比转换成该组的 flex 样式。
 * 用 inline style 而不是 class，是为了绕开 Bootstrap 只有 col-sm-1..12 的限制。
 */
function apply_flex_basis(cols, pct) {
	cols.forEach((col) => {
		const $col = $(col);
		// 清掉 Frappe 原本的 col-sm-* 类，改用 inline flex。
		// 注意：不能 $col.removeClass()，那会连 hide-control 一起清掉。
		$col.removeClass(
			"col-sm-0 col-sm-1 col-sm-2 col-sm-3 col-sm-4 col-sm-5 col-sm-6 col-sm-7 " +
				"col-sm-8 col-sm-9 col-sm-10 col-sm-11 col-sm-12 col-sm-20"
		);
		$col.addClass("form-column");
		$col[0].style.flex = `0 0 ${pct}%`;
		$col[0].style.maxWidth = `${pct}%`;
		$col[0].style.width = `${pct}%`;
	});
}

/** 恢复 Frappe 原始的 col-sm-* 布局（把 inline style 抹掉） */
function reset_to_frappe(cols) {
	cols.forEach((col) => {
		const el = col;
		el.style.flex = "";
		el.style.maxWidth = "";
		el.style.width = "";
	});
}

/* ---------------------------------------------------------------------------
 * 2. 核心：重排一个 Section 的列宽
 * ------------------------------------------------------------------------- */

/**
 * @param {Object} section  frappe.ui.form.Section 实例
 */
function relayout_section(section) {
	const cols = get_columns(section);
	if (!cols.length) return;

	const key = section_key(section);

	// 2.1 跳过名单
	if (LAYOUT_CONFIG.skip_sections.includes(key)) {
		reset_to_frappe(cols);
		return;
	}

	// 2.2 优先：显式的每列百分比（section_widths）
	if (key && LAYOUT_CONFIG.section_widths[key]) {
		const pcts = LAYOUT_CONFIG.section_widths[key];
		cols.forEach((col, i) => {
			const pct = pcts[i] !== undefined ? pcts[i] : pcts[pcts.length - 1];
			apply_flex_basis([col], pct);
		});
		return;
	}

	// 2.3 次优先：显式的每行列数（section_rows）
	//     例如 [5,2,4] → 前 5 个 20%、接下来 2 个 50%、再 4 个 25%
	if (key && LAYOUT_CONFIG.section_rows[key]) {
		const rowCounts = LAYOUT_CONFIG.section_rows[key];
		let idx = 0;
		rowCounts.forEach((count) => {
			const pct = 100 / count;
			const group = cols.slice(idx, idx + count);
			apply_flex_basis(group, pct);
			idx += count;
		});
		// 剩余列（配置没覆盖到的）按最后一行的宽度
		if (idx < cols.length) {
			const lastCount = rowCounts[rowCounts.length - 1] || 1;
			apply_flex_basis(cols.slice(idx), 100 / lastCount);
		}
		return;
	}

	// 2.4 默认：全局 default_per_row
	const perRow = LAYOUT_CONFIG.default_per_row;
	if (!perRow) {
		reset_to_frappe(cols);
		return;
	}
	apply_flex_basis(cols, 100 / perRow);
}

/* ---------------------------------------------------------------------------
 * 3. 接入 Frappe 生命周期
 * ------------------------------------------------------------------------- */

/*
 * 3.1 首选：覆盖 frappe.ui.form.Layout.prototype.render()
 *     render() 是所有字段被分配到 Section/Column 的地方，
 *     结束后所有 .form-column 已经在 DOM 里，可以直接量宽度。
 *
 * 注意：frappe.ui.form.Layout 是全局对象（layout.js:5），
 *       所以这个 patch 入口是稳定的、官方的扩展点。
 */
/* ============================================================================
   延迟执行工具
   ---------------------------------------------------------------------------
   为什么需要：app_include_js 的 script 由 assets.js 动态插入，
   执行时机可能早于 form.bundle.js —— 此时 frappe.ui.form.Layout 尚未定义，
   patch 会被直接跳过（用户表现为「完全没变化」）。
   这里改成轮询等待（最多 30 秒），Layout 一出现就立刻打补丁。
   ============================================================================ */
function defer_until_layout(fn, label) {
	var tries = 0;
	function attempt() {
		if (window.frappe && frappe.ui && frappe.ui.form && frappe.ui.form.Layout) {
			try {
				fn();
			} catch (e) {
				console.error("[layout-patch] " + label + " failed", e);
			}
			return;
		}
		if (++tries > 300) {
			console.warn("[layout-patch] " + label + ": 等待 frappe.ui.form.Layout 超时（30s）");
			return;
		}
		setTimeout(attempt, 100);
	}
	attempt();
}

/* ============================================================================
   放开 Form 页面的宽度上限（Frappe --page-max-width，默认 900px）
   ---------------------------------------------------------------------------
   Frappe 全局规则：
       body:not(.full-width) .std-form-layout .section-body {
           max-width: var(--page-max-width);
       }
   → 子表 11 列（合计 958px）在 900px 里放不下 → 横向滚动条。

   Frappe 的官方开关是给 body 加 .full-width 类。
   放在这里用 JS 做（而不是 doctype CSS），因为 doctype CSS 走 meta.__css，
   会被浏览器/localStorage 缓存，调试时经常不生效。

   只对「本页有 Section 超过 900px 的内容」生效 —— 用 --page-max-width: none
   覆盖 CSS 变量，比直接改 max-width 更干净（Frappe 自己就是这么用的）。
   ============================================================================ */
function unlock_page_width() {
	if (!document.body) return;
	// 只解锁「本 app 的表单页」（.std-form-layout 存在）
	if (!document.querySelector(".std-form-layout")) {
		document.body.classList.remove("full-width");
		return;
	}
	document.body.classList.add("full-width");
}

/* ============================================================================
   子表 Grid 的列宽自适应
   ---------------------------------------------------------------------------
   问题：Frappe v16 的 grid 列写死 `flex: 1 0 <width>px`（flex-shrink: 0），
        11 列合计 958px + row-check(31) + row-actions(46) + 尾部 col(30)
        = 1067px，而可用宽度只有 926px → 横向滚动条。

   修法：让 grid 的业务列可以收缩（flex-shrink: 1），
        并按比例分配剩余空间。表格列宽不再溢出。

   只作用于 .grid-body / .grid-heading-row 里的「业务列」
   （即带 data-fieldname 且不是 row-check / row-actions / row-index 的列）。
   ============================================================================ */
function make_grid_columns_flexible() {
	var grids = document.querySelectorAll(".grid-body, .grid-heading-row");
	grids.forEach(function (grid) {
		var rows = grid.querySelectorAll(".data-row, .grid-row");
		rows.forEach(function (row) {
			// Frappe 的 CSS：.data-row.row { width: max-content; }
			// → 行宽 = 各列宽之和（1067px），子列没有可收缩空间。
			// 覆盖成 width:100% + min-width:0，flex 收缩才生效。
			// 必须用 setProperty(..., "important")，因为是 CSS 规则不是 inline style。
			// 只在值偏离时写 —— 写完值就对了，MutationObserver 不会再次触发
			// （attributeFilter 含 "style"，但值不变时 setProperty 不会产生 mutation）
			if (getComputedStyle(row).width !== row.parentElement.clientWidth + "px" || row.style.width !== "100%") {
				row.style.setProperty("width", "100%", "important");
				row.style.setProperty("min-width", "0", "important");
			}
			var cols = row.querySelectorAll("[data-fieldname]");
			cols.forEach(function (col) {
				var fn = col.getAttribute("data-fieldname");
				if (!fn) return;
				if (fn === "row-check" || fn === "row-actions" || fn === "row-index") return;
				// 注意：业务列也带 .grid-static-col，不能按 class 过滤，
				//       只能按 data-fieldname 判断。
				// 允许收缩，并按原宽度比例分配剩余空间
				// （flex-grow = 原宽度 → 比例保持；flex-shrink = 1 → 可压缩）
				var basis = col.style.flexBasis || "80px";
				var grow = parseInt(basis, 10) || 80;
				var want = grow + " 1 " + basis;
				if (col.style.flex !== want || col.style.maxWidth !== "none") {
					col.style.setProperty("flex", want, "important");
					col.style.setProperty("max-width", "none", "important");
				}
			});
		});
	});
}

defer_until_layout(function patch_grid_flex() {
	make_grid_columns_flexible();
	var obs = new MutationObserver(function () {
		clearTimeout(patch_grid_flex._t);
		patch_grid_flex._t = setTimeout(make_grid_columns_flexible, 50);
	});
	obs.observe(document.documentElement, {
		subtree: true,
		childList: true,
		attributes: true,
		attributeFilter: ["style", "class"]
	});
	console.log("[layout-patch] grid columns made flexible");
});

defer_until_layout(function patch_page_width() {
	unlock_page_width();
	// 表单切换时重新执行
	const obs = new MutationObserver(function () {
		unlock_page_width();
	});
	obs.observe(document.body, { childList: true, subtree: true });
	console.log("[layout-patch] page width unlocked (body.full-width)");
});

defer_until_layout(function patch_layout_render() {

	const OriginalRender = frappe.ui.form.Layout.prototype.render;

	frappe.ui.form.Layout.prototype.render = function (new_fields) {
		const ret = OriginalRender.apply(this, arguments);

		// render 之后才拿得到所有 section
		(this.sections || []).forEach((section) => {
			try {
				relayout_section(section);
			} catch (e) {
				console.error("[layout-patch] relayout_section failed", e);
			}
		});

		return ret;
	};

	console.log("[layout-patch] frappe.ui.form.Layout.prototype.render patched");
});

/*
 * 3.2 兜底：字段依赖隐藏/显示后，Frappe 会调用 Column.refresh()
 *     → resize_all_columns() 重新计算，会覆盖我们的 inline style。
 *     所以要在 refresh 之后再补一次。
 *
 *     Column 是 ES module，不是全局。拿不到它的 prototype，
 *     但可以在 Layout.refresh() 之后统一重排（refresh 是全局可 patch 的）。
 */
defer_until_layout(function patch_layout_refresh() {

	const OriginalRefresh = frappe.ui.form.Layout.prototype.refresh;

	frappe.ui.form.Layout.prototype.refresh = function (doc) {
		const ret = OriginalRefresh.apply(this, arguments);

		// 用 setTimeout(0) 等 Frappe 内部的 refresh_dependency → column.refresh()
		// → resize_all_columns() 跑完，再重新覆盖。
		setTimeout(() => {
			(this.sections || []).forEach((section) => {
				try {
					relayout_section(section);
				} catch (e) {
					/* noop */
				}
			});
		}, 0);

		return ret;
	};

	console.log("[layout-patch] frappe.ui.form.Layout.prototype.refresh patched");
});

/*
 * 3.3 兜底：字段 depends_on 变化会触发 Column.refresh()（单列），
 *     不经过 Layout.refresh()。用 MutationObserver 监听 class 变化，
 *     发现 .form-column 的 class 被 Frappe 改了就重排。
 *     （轻量，只在 class 属性变化时触发）
 */
defer_until_layout(function patch_mutation_observer() {
	if (!window.MutationObserver || !window.frappe) return;

	const observer = new MutationObserver((mutations) => {
		let need = false;
		for (const m of mutations) {
			if (m.type === "attributes" && m.attributeName === "class") {
				const t = m.target;
				if (t && t.classList && t.classList.contains("form-column")) {
					need = true;
					break;
				}
			}
		}
		if (!need) return;

		// 去抖
		clearTimeout(patch_mutation_observer._t);
		patch_mutation_observer._t = setTimeout(() => {
			document.querySelectorAll(".form-section").forEach((secEl) => {
				// 找到对应的 Section 实例（通过 fields_dict 反查不可靠，直接按 DOM 处理）
				const cols = Array.from(secEl.querySelectorAll(":scope > .section-body > .form-column"));
				if (!cols.length) return;
				const key = secEl.getAttribute("data-fieldname");
				applyConfigFor(key, cols);
			});
		}, 20);
	});

	observer.observe(document.documentElement, {
		subtree: true,
		attributes: true,
		attributeFilter: ["class"],
	});

	/** 按 DOM 上的 data-fieldname 应用配置（供 MutationObserver 用） */
	function applyConfigFor(key, cols) {
		if (!key) return;
		if (LAYOUT_CONFIG.skip_sections.includes(key)) {
			reset_to_frappe(cols);
			return;
		}
		if (LAYOUT_CONFIG.section_widths[key]) {
			const pcts = LAYOUT_CONFIG.section_widths[key];
			cols.forEach((col, i) => {
				const pct = pcts[i] !== undefined ? pcts[i] : pcts[pcts.length - 1];
				apply_flex_basis([col], pct);
			});
			return;
		}
		if (LAYOUT_CONFIG.section_rows[key]) {
			const rowCounts = LAYOUT_CONFIG.section_rows[key];
			let idx = 0;
			rowCounts.forEach((count) => {
				apply_flex_basis(cols.slice(idx, idx + count), 100 / count);
				idx += count;
			});
			if (idx < cols.length) {
				const lastCount = rowCounts[rowCounts.length - 1] || 1;
				apply_flex_basis(cols.slice(idx), 100 / lastCount);
			}
			return;
		}
		const perRow = LAYOUT_CONFIG.default_per_row;
		if (perRow) apply_flex_basis(cols, 100 / perRow);
	}

	console.log("[layout-patch] MutationObserver armed");
});

/* ---------------------------------------------------------------------------
 * 4. 对外 API：给单个 DocType 临时改布局（例如只针对某张单据）
 * ------------------------------------------------------------------------- */
window.frappe.layout_patch = {
	config: LAYOUT_CONFIG,

	/** 立即对当前打开的表单重排 */
	refresh(frm) {
		const layout = frm && frm.layout;
		if (!layout) return;
		(layout.sections || []).forEach((section) => relayout_section(section));
	},

	/** 为某个 Section 设置「每行几个」 */
	setRows(section_fieldname, rowCounts) {
		LAYOUT_CONFIG.section_rows[section_fieldname] = rowCounts;
	},

	/** 为某个 Section 设置「每列百分比」 */
	setWidths(section_fieldname, pcts) {
		LAYOUT_CONFIG.section_widths[section_fieldname] = pcts;
	},

	/** 恢复 Frappe 原始布局 */
	reset(section_fieldname) {
		delete LAYOUT_CONFIG.section_rows[section_fieldname];
		delete LAYOUT_CONFIG.section_widths[section_fieldname];
		// 立刻把该 Section 的 inline style 抹掉，并让 Frappe 重算 col-sm-*
		document
			.querySelectorAll(`.form-section[data-fieldname="${section_fieldname}"]`)
			.forEach((secEl) => {
				const cols = Array.from(
					secEl.querySelectorAll(":scope > .section-body > .form-column")
				);
				reset_to_frappe(cols);
				// 触发 Frappe 重新按原始规则计算 col-sm-*
				cols.forEach((col) => {
					// 触发 Frappe 重新按原始规则计算 col-sm-*
					const total = cols.length || 1;
					let colspan = Math.floor(12 / total);
					if (total == 5) colspan = 20;
					const wasHidden = col.classList.contains("hide-control");
					col.className = "form-column";
					col.classList.add("col-sm-" + colspan);
					if (wasHidden) col.classList.add("hide-control");
				});
			});
	},
};


