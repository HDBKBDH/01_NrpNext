/**
 * 隐藏不需要的 App 入口
 *
 * 背景：Frappe v16 的 All Apps 页面由 add_to_apps_screen hook 驱动，
 * 没有 site 级的"隐藏某个 app"开关：
 *   frappe.permissions.check_app_permission 要求 System Manager 角色
 *   erpnext.check_app_permission 对 Administrator 恒返回 True
 * 都改不了。所以只能在展示层处理。
 *
 * 时机踩过的坑：
 *   frappe.ready() 在 desk 页面可能已经触发过了（boot 早就完成），
 *   导致回调不执行 → 隐藏失效。
 *   所以改成：立刻执行一次 + ready 再执行一次 + 监听 DOM 变化。
 *
 * 影响范围：仅隐藏 All Apps 页面的入口图标。
 * DocType、路由、权限全部照常可用（直接输 URL 或用搜索都能进）。
 * 数据不会被删除。
 *
 * 需要恢复时：从 HIDDEN_APPS 里删掉对应项即可。
 */

const HIDDEN_APPS = ["erpnext", "frappe"];

function hideHiddenApps() {
	const app_data = (window.frappe && frappe.boot && frappe.boot.app_data) || [];

	for (const app of app_data) {
		if (HIDDEN_APPS.includes(app.app_name)) {
			app.on_apps_screen = false;
		}
	}
}

// 立刻执行（boot 可能已完成）
hideHiddenApps();

// frappe.ready 兜底
if (window.frappe) {
	frappe.ready(hideHiddenApps);
	frappe.after_ajax && frappe.after_ajax(hideHiddenApps);
}

// All Apps 页面渲染后，DOM 里可能已存在图标 → 直接藏 DOM
function hideIconsInDom() {
	const titles = ["ERPNext", "Framework"];
	for (const t of titles) {
		const nodes = document.querySelectorAll(
			`.desktop-icon, .app-icon, .icon-container`
		);
		for (const n of nodes) {
			const cap = n.closest(".desktop-icon") || n.parentElement;
			if (!cap) continue;
			const text = (cap.textContent || "").trim();
			const img = cap.querySelector("img");
			const src = img ? img.getAttribute("src") || "" : "";
			if (
				text.includes(t) ||
				src.includes("/erpnext/") ||
				src.includes("/frappe/")
			) {
				cap.style.display = "none";
			}
		}
	}
}

if (document.readyState === "loading") {
	document.addEventListener("DOMContentLoaded", hideIconsInDom);
} else {
	hideIconsInDom();
}

if (window.frappe) {
	frappe.ready(hideIconsInDom);
}

// All Apps 页面是 SPA 路由，用 MutationObserver 兜底
const observer = new MutationObserver(() => {
	hideHiddenApps();
	hideIconsInDom();
});
observer.observe(document.documentElement, {
	childList: true,
	subtree: true,
});
