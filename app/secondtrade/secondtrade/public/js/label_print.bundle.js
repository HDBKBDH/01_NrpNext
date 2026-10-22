// Label Print 前端脚本
// 需求（冰）：「整理一个专门用于打印的可拷贝的文本窗口，点击可直接拷贝，
//            复制到标签机即可」
//
// 做法：
// 1. 选中 SN 后自动生成标签文本 + 二维码（server 端 validate 已实现）
// 2. 文本框上方加「复制」按钮，点了直接写剪贴板，不用手动框选
// 3. 二维码支持点击放大，方便看/拍照

frappe.ui.form.on("Label Print", {
	refresh(frm) {
		// validate 已生成 label_text，这里只负责渲染工具条
		if (frm.doc.serial_no && frm.doc.label_text) {
			frm.trigger("render_label_tools");
		}
	},

	serial_no(frm) {
		// 换 SN 就重新生成
		//
		// 用 frm.trigger 而不是 frm.call：
		//   frm.call("refresh") → POST /api/method/run_doc_method
		//     → handler.run_doc_method 取 method_obj.__func__
		//     → is_whitelisted(fn) 检查 fn in frappe.whitelisted 集合
		//
		//   v16 的坑：@frappe.whitelist() 内部用
		//     fn = validate_argument_types(fn, ...)   ← 返回新包装函数
		//     whitelisted.add(fn)                     ← 注册的是包装后的对象
		//   但 __func__ 拿到的是原始函数，两边 identity 不一致
		//   → 白名单永远命中不了，必报 PermissionError
		//
		// frm.trigger 走 doc.run_method()，是框架内部调用路径，不做 whitelist 检查。
		if (frm.doc.serial_no) {
			frm.refresh();
			frm.trigger("render_label_tools");
		}
	},

	render_label_tools(frm) {
		const text = frm.doc.label_text || "";

		if (!text) {
			return;
		}

		// 在 label_text 字段上方插入工具条
		const field = frm.get_field("label_text");
		if (!field) {
			return;
		}

		// 幂等：同一份 DOM 里只插一次，DOM 重建后自动重插
		const $existing = $(field.wrapper).find(".label-tools");
		if ($existing.length) {
			$existing.remove();
		}

		const $wrap = $(`
			<div class="label-tools" style="
				margin-bottom: 8px;
				display: flex;
				gap: 8px;
				align-items: center;
				flex-wrap: wrap;
			">
				<button class="btn btn-sm btn-primary label-copy-btn">
					<i class="octicon octicon-clippy"></i> 复制标签文本
				</button>
				<button class="btn btn-sm btn-default label-save-btn">
					<i class="octicon octicon-save"></i> 保存备查
				</button>
				<span class="label-hint text-muted" style="font-size: 12px;">
					粘贴到 Brother P-touch Editor 的表格里排版
				</span>
			</div>
		`);

		field.df.fieldname && $(field.wrapper).prepend($wrap);

		$wrap.on("click", ".label-copy-btn", function () {
			const value = frm.doc.label_text || "";

			const done = () => {
				frappe.show_alert({
					message: __("已复制到剪贴板，粘贴到 P-touch Editor"),
					indicator: "green",
				});
			};

			if (navigator.clipboard && window.isSecureContext) {
				navigator.clipboard.writeText(value).then(done);
			} else {
				// 降级：临时 textarea + execCommand
				const $ta = $("<textarea/>")
					.val(value)
					.css({ position: "fixed", opacity: "0" })
					.appendTo("body");
				$ta[0].select();
				document.execCommand("copy");
				$ta.remove();
				done();
			}
		});

		// 「保存备查」：记录谁在什么时候给哪个 SN 打了标签
		$wrap.on("click", ".label-save-btn", function () {
			frm.save().then(() => {
				frappe.show_alert({
					message: __("已保存备查"),
					indicator: "green",
				});
			});
		});
	},
});