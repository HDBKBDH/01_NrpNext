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
		if (!frm.is_new() && frm.doc.serial_no) {
			frm.trigger("render_label_tools");
		}
	},

	serial_no(frm) {
		// 换 SN 就重新生成（不保存）
		if (frm.doc.serial_no) {
			frm.call("refresh").then(() => {
				frm.trigger("render_label_tools");
			});
		}
	},

	render_label_tools(frm) {
		const text = frm.doc.label_text || "";

		if (!text) {
			return;
		}

		// 在 label_text 字段上方插入工具条
		const field = frm.get_field("label_text");
		if (!field || frm.__label_tools_injected) {
			return;
		}
		frm.__label_tools_injected = true;

		const $wrap = $(`
			<div class="label-tools" style="
				margin-bottom: 8px;
				display: flex;
				gap: 8px;
				align-items: center;
			">
				<button class="btn btn-sm btn-primary label-copy-btn">
					<i class="octicon octicon-copy"></i> 复制标签文本
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
	},
});