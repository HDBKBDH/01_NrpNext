/**
 * 隐藏不需要的 App 入口（ERPNext / Framework）
 *
 * 背景：Frappe v16 的 All Apps 页面由 add_to_apps_screen hook 驱动，
 * 没有 site 级的"隐藏某个 app"开关：
 *   frappe.permissions.check_app_permission 要求 System Manager 角色
 *   erpnext.check_app_permission 对 Administrator 恒返回 True
 * 都改不了，所以只能在展示层处理。
 *
 * 时机踩过的坑：
 *   本文件在 erpnext.bundle.js 之后加载，但 frappe.boot 可能还没就绪；
 *   等 boot 就绪后 frappe.ready 又可能已经触发过了（回调不跑）。
 *   → 三个兜底：立即执行 + 轮询等 boot + MutationObserver。
 *
 * 影响范围：仅隐藏 All Apps 页面的入口图标。
 * DocType、路由、权限全部照常可用（直接输 URL 或用搜索都能进）。
 * 数据不会被删除。
 *
 * 需要恢复时：从 HIDDEN_APPS 里删掉对应项即可。
 */

const HIDDEN_APPS = ["erpnext", "frappe"];

function hideHiddenApps() {
	if (!window.frappe || !frappe.boot || !frappe.boot.app_data) {
		return false;
	}

	for (const app of frappe.boot.app_data) {
		if (HIDDEN_APPS.includes(app.app_name)) {
			app.on_apps_screen = false;
		}
	}
	return true;
}

function hideIconsInDom() {
	for (const n of document.querySelectorAll(".desktop-icon, .app-icon, .icon-container")) {
		const cap = n.closest(".desktop-icon") || n.parentElement;
		if (!cap || cap.style.display === "none") continue;

		const text = (cap.textContent || "").trim();
		const img = cap.querySelector("img");
		const src = img ? img.getAttribute("src") || "" : "";

		const hide =
			text.includes("ERPNext") ||
			text.includes("Framework") ||
			src.includes("/erpnext/") ||
			src.includes("/frappe/");

		if (hide) {
			cap.style.display = "none";
		}
	}
}

function applyAll() {
	hideHiddenApps();
	hideIconsInDom();
}

// 1. 立即尝试（boot 可能已就绪）
applyAll();

// 2. 轮询等 boot 就绪（最多 10 秒）
let tries = 0;
const timer = setInterval(() => {
	tries++;
	if (hideHiddenApps() || tries > 100) {
		clearInterval(timer);
	}
	hideIconsInDom();
}, 100);

// 3. frappe.ready 兜底
if (window.frappe) {
	frappe.ready(applyAll);
	frappe.after_ajax && frappe.after_ajax(applyAll);
}

// 4. DOM 变化兜底（All Apps 是 SPA 路由，图标后渲染）
const observer = new MutationObserver(applyAll);
observer.observe(document.documentElement, { childList: true, subtree: true });
