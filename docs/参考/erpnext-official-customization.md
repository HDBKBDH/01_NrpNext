# ERPNext/Frappe 定制化与扩展机制（v16 源码验证）

> **本文所有「实际支持」的列表均来自 Frappe v16 源码，非记忆。**
> 来源：
> - `frappe/custom/doctype/custom_field/custom_field.json`（fieldtype 列表、属性字段）
> - `frappe/custom/doctype/custom_field/custom_field.py`（Property Setter 属性白名单、验证逻辑）
> - `frappe/custom/doctype/custom_field/custom_field.py` 的 `docfield_properties` 字典
>
> 目标站点：ERPNext/Frappe **v16.52.0**

---

## 0. 一句话原则

**能用 Property Setter 改标准字段属性，就不要用 Custom Field 新建字段。**
Custom Field 意味着一个新列 = 第二个真源 = 以后必然要同步。

---

## 1. v16 实际支持的 fieldtype 完整列表（44 个）

来源：`custom_field.json` → `fieldtype` 字段的 `options`。

```
Autocomplete        Attach              Attach Image        Attachment Gallery
Barcode             Button              Check               Code
Color               Column Break        Currency            Data
Date                Datetime            Duration            Dynamic Link
Float               Fold                Geolocation         Heading
HTML                HTML Editor         Icon                Image
Int                 JSON                Link                Long Text
Markdown Editor     Password            Percent             Phone
Read Only           Rating              Section Break       Select
Signature           Small Text          Tab Break           Table
Table MultiSelect   Text                Text Editor         Time
```

### ⚠️ 没有 `Virtual` 这个 fieldtype

传 `fieldtype: "Virtual"` 会被拒：
```
Field Type cannot be "Virtual"
```

**但 Virtual 概念是存在的** —— 它是 Custom Field 的一个**独立 Check 属性** `is_virtual`，
不是 fieldtype。含义：该字段不落库（不建列），只在表单上显示。

源码（`custom_field.py:405`）：
```python
elif prop == "is_virtual" and meta_df[0].get("is_virtual") == 0 and df.get("is_virtual") == 1:
    frappe.msgprint(_("You can't set standard field {0} as virtual").format(...))
    return False
```
→ **标准字段不能改成 virtual**，只能新建的 Custom Field 用。

源码（`custom_field.py:580`）：
```python
def validate_fieldtype_change(self, df, old_value, new_value):
    if df.is_virtual:
        return          # virtual 字段跳过 fieldtype 变更校验
```

### 关键区分

| 概念 | 位置 | 落库 | 用途 |
|---|---|---|---|
| `fieldtype: "Read Only"` | fieldtype 列表里 | **是**（建列） | 只读显示 |
| `is_virtual: 1` | Custom Field 的 Check 属性 | **否**（不建列） | 纯展示，计算值 |

**「计算出来的只读字段」= `is_virtual=1` + 任意 fieldtype（通常是 Data）**，
配合 Client Script / Server Script 赋值，不存数据库。

⚠️ 这意味着 virtual 字段的值**不会持久化**，每次加载都要重新算。

---

## 2. Property Setter：能改哪些属性（源码白名单）

来源：`custom_field.py` 的 `docfield_properties`（第 766-821 行）。

### 字段级属性（`doctype_or_field = "DocField"`）

```python
docfield_properties = {
    # 布局
    "idx": "Int", "label": "Data", "width": "Data", "print_width": "Data",
    "columns": "Int", "alignment": "Select", "collapsible": "Check",
    "collapsible_depends_on": "Data", "hide_border": "Check",

    # 可见性 ★
    "hidden": "Check", "in_list_view": "Check",
    "in_standard_filter": "Check", "in_global_search": "Check",
    "in_preview": "Check", "print_hide": "Check",
    "print_hide_if_no_value": "Check", "report_hide": "Check",

    # 可编辑性 ★
    "read_only": "Check", "set_only_once": "Check",
    "allow_on_submit": "Check", "allow_in_quick_entry": "Check",
    "allow_bulk_edit": "Check", "no_copy": "Check",

    # 校验
    "reqd": "Check", "unique": "Check", "non_negative": "Check",
    "mandatory_depends_on": "Data", "read_only_depends_on": "Data",
    "depends_on": "Data", "length": "Int",

    # 取值
    "default": "Text", "options": "Text", "fetch_from": "Small Text",
    "fetch_if_empty": "Check", "precision": "Select",

    # 权限
    "permlevel": "Int", "ignore_user_permissions": "Check",

    # 其他
    "fieldtype": "Select",     # ★ 见下方警告
    "is_virtual": "Check", "translatable": "Check", "bold": "Check",
    "placeholder": "Data", "mask": "Check", "button_color": "Select",
    "link_filters": "JSON", "auto_repeat": "Link",
    "remember_last_selected_value": "Check", "sort_options": "Check",
    "show_dashboard": "Check", "ignore_xss_filter": "Check",
    "description": "Text", "in_import_template": "Check",
    "hide_days": "Check", "hide_seconds": "Check",
}
```

### ⚠️ `fieldtype` 在白名单里，但改它有严格限制

源码 `validate_fieldtype_change` → `allow_fieldtype_change(old, new)` 逐对校验，
且 `is_virtual=1` 的字段直接跳过校验（不会落库所以无所谓）。

**实际后果**：改 fieldtype 可能需要改数据库列类型，
生产环境改之前先在测试站点验证。

### DocType 级属性（`doctype_or_field = "DocType"`）

白名单在同一个文件的上方（`doctype_properties`），包含：
```
istable, issingle, is_submittable, editable_grid, allow_copy,
track_changes, track_seen, track_all_views, engine, is_virtual,
istable ...
```

### `doctype_or_field` 的含义（必填，不填会报错）

| 值 | 改什么 |
|---|---|
| `"DocField"` | 某个字段的属性 ← **我们用这个** |
| `"DocType"` | 整个 DocType 的属性 |

报错信息：
```
[Property Setter, Company-default_warehouse-in_list_view]: doctype_or_field
```

### 模板

```python
frappe.get_doc({
    "doctype": "Property Setter",
    "doctype_or_field": "DocField",
    "doc_type": "Company",
    "field_name": "default_warehouse",
    "property": "in_list_view",     # 白名单里的 key
    "value": "1",
    "property_type": "Check",       # 值的类型，见白名单
}).insert(doctype="Property Setter")
```

ERPNext 自己就这么用（`tabProperty Setter` 现成数据）：
```
('Item', 'item_group', 'in_list_view', '1')
('Item', 'stock_uom',   'in_list_view', '1')
```

---

## 3. Customize Form / Custom Field 的属性清单

来源：`custom_field.json` 的全部字段。

### 定位类
| 字段 | 类型 | 说明 |
|---|---|---|
| `dt` | Link→DocType | 挂在哪个 DocType 上 |
| `fieldname` | Data | 字段名（**不能与已有字段冲突**） |
| `label` | Data | 显示标签（中文） |
| `insert_after` | Select | 插入到哪个字段之后 |
| `module` | Link→Module | 仅用于导出 |

### 行为类
| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `fieldtype` | Select | Data | 见上方 44 个列表 |
| `options` | Small Text | — | Select 的选项 / Link 的目标 DocType / Table 的子表 |
| `default` | Text | — | 默认值 |
| `reqd` | Check | 0 | 必填 |
| `unique` | Check | 0 | 唯一 |
| `read_only` | Check | 0 | 只读 |
| `set_only_once` | Check | 0 | 提交后禁止改 |
| `allow_on_submit` | Check | 0 | **子表字段**：提交后可改 |
| `depends_on` | Code | — | 显示条件（JS 表达式） |
| `mandatory_depends_on` | Code | — | 必填条件 |
| `read_only_depends_on` | Code | — | 只读条件 |
| `fetch_from` | Small Text | — | 取值来源 `link_field.field` |
| `fetch_if_empty` | Check | 0 | 仅当为空时 fetch |

### 显示类
| 字段 | 默认 | 说明 |
|---|---|---|
| `hidden` | 0 | 隐藏 |
| `in_list_view` | 0 | **列表页显示这一列** |
| `in_standard_filter` | 0 | **列表页顶部筛选框** |
| `in_global_search` | 0 | 全局搜索索引 |
| `in_preview` | 0 | 文档预览显示 |
| `width` / `columns` / `alignment` | — | 布局 |
| `collapsible` + `collapsible_depends_on` | 0 | 可折叠分组 |

### 其他常用
| 字段 | 说明 |
|---|---|
| `permlevel` | 权限层级（0=所有人，1=特定角色…） |
| `ignore_user_permissions` | 忽略 User Permission 过滤 |
| `link_filters` (JSON) | Link 字段的下拉过滤 |
| `placeholder` | 输入框占位文字 |
| `translatable` | 可翻译（Select 选项） |
| `is_virtual` | **不落库，纯展示** |
| `no_copy` | 复制单据时不带此字段 |
| `print_hide` / `print_hide_if_no_value` / `report_hide` | 打印/报表隐藏 |
| `mandatory_depends_on` / `read_only_depends_on` | 条件必填/只读 |

---

## 4. Customize Form 的能力边界

### ✅ 能改（标准字段的属性）
所有 `docfield_properties` 白名单里的属性 —— 用 Property Setter 或 Customize Form 界面。

### ❌ 不能改
| 想改 | 后果 |
|---|---|
| `fieldname` | 主键/字段名不可改；要改必须写 patch `ALTER TABLE` |
| 主键 `name` 的生成规则 | 只能通过 DocType 的 `autoname` 或 patch |
| DocType 的 `istable` / `issingle` | 需要改 DocType 定义 + migrate |
| 已落库字段的 `fieldtype` | 有限制（见上），生产环境慎改 |

**结论：Customize Form 界面能做的，Property Setter 都能做；
反过来 Property Setter 能做的，界面不一定方便。**

---

## 5. Client Script vs Server Script vs Controller

| | Client Script | Server Script | Controller (Python) |
|---|---|---|---|
| 运行位置 | 浏览器 | 服务端（沙箱） | 服务端（完整） |
| 触发时机 | 前端事件 | 前端事件 → 服务端 | DocType 生命周期 |
| 能访问 DB | ❌ 只能调 API | ✅ 受限 | ✅ 完整 |
| 能 import | ❌ | ❌ 白名单内 | ✅ 任意 |
| 性能 | 快（无网络往返） | 慢（一次往返） | 快 |
| 适合 | 字段联动、按钮 UI | 简单计算、调用 API | 复杂业务逻辑、批量操作 |

### Client Script 的 doc_events 触发时机

```javascript
frappe.ui.form.on("Item", {
    onload(frm) {                    // 表单加载
    },
    refresh(frm) {                   // 每次刷新（含字段变化后）
    },
    item_code(frm, cdt, cdn) {       // 字段变化时（fieldname 必须是真实字段名）
    },
    setup(frm) {                     // 初始化，最先执行
    },
    validate(frm) {                  // 保存前校验，返回 Promise 可异步
    },
    before_save(frm) {               // 保存前
    },
    after_save(frm) {                // 保存后
    },
    on_submit(frm) {                 // 提交后
    },
});
```

⚠️ `fieldname(frm, cdt, cdn)` 里的字段名必须是**真实存在的字段**，
写错不报错，只是永远不触发。

### Client Script 常用 API

```javascript
// 设置值（会触发后端 validate）
frm.set_value("warehouse", "JP - ISTK - ISTK");

// 仅前端赋值，不触发后端
frm.set_value({fieldname: "x", value: 1}, function(){});

// 读取值
const v = frm.doc.warehouse;

// 过滤 Link 下拉
frm.set_query("item_code", function() {
    return {filters: {item_group: "J2C_ISTK"}};
});

// 刷新
frm.refresh();

// 弹确认框
frm.confirm("确定吗？", () => { /* ... */ });
```

### Server Script（`frappe.script_manager.doctype`）

在界面上写服务端 JS，**没有 `import` 能力**，
只能用白名单里的对象（`frappe`、`doc` 等）。

**不适合**：复杂逻辑、批量操作、需要 import 的场景。
**优先**：简单取值计算、调用已有 whitelisted 方法。

---

## 6. 保存后何时生效

源码验证（`custom_field.py`）：

```python
# 第 214 行
frappe.translate.clear_cache()
# 第 259 行
frappe.clear_cache(doctype=self.doc_type)
# 第 653 行
frappe.clear_cache(doctype=doctype)
# 第 710 行
frappe.clear_cache(doctype=doctype)
```

→ **保存 Custom Field / Property Setter 会自动清缓存，不需要手动清。**

但如果改了 **DocType 定义本身**（JSON），需要 `bench migrate`。

⚠️ 若改完浏览器仍显示旧状态，先确认是不是 **boot payload 的 Redis 缓存**
（见主 SKILL pitfall 63）—— 那是另一个缓存层，`frappe.clear_cache` 管不到。

---

## 7. 打印机制

| 机制 | 用途 |
|---|---|
| **Print Format** | 标准单据的打印模板，可自定义 HTML 布局，支持 Jinja |
| **Print Template Builder** | 图形化构建 Print Format |
| **Letter Print** | 独立文档（Letter / Email Account），不走库存 |

Print Format 通过 `Custom Field` 或独立 DocType 关联到业务单据。

---

## 8. Workspace / Module Def / Dock

| 对象 | 作用 |
|---|---|
| **Workspace** | 工作台页面 + 侧栏项。JSON 位置：`<app>/workspace/<module>/<module>.json` |
| **Workspace.links** | 侧栏项，`type` ∈ {`Link`, `Card Break`}，目标在 `link_to` + `link_type: "DocType"` |
| **Module Def** | 模块定义，含 `custom` 标记（Module Def 不能直接 rename，需先 `custom=1`） |
| **Dock** | v16 的导航层，JSON 位置：`<app>/dock/<app>/<app>.json` |

**Workspace 的 links 可以指向任意 DocType（不限本模块）** —— ERPNext 自己就这么做：
```
Manufacturing: Item      (link_type=DocType)
Manufacturing: Warehouse (link_type=DocType)
```

详细规则见主 SKILL pitfall 45 / 48 / 57。

---

## 9. 翻译：让 DocType 显示中文

**问题**：字段 `label` 写中文就能显示中文，但 **DocType 的 `name`**
（菜单项、搜索框、Workspace 链接）显示的是英文 —— 因为 v16 的 `tabDocType`
**没有 `label` 或 `translated` 列**可以回退。

**解决**：翻译 DocType 名称（`msgid "Label Print"` / `msgstr "标签打印"`）

```bash
# 生成 pot 模板
bench generate-pot-file --app <app>

# 编辑 <app>/locale/zh.po（或自己写）

# 编译（注意：没有 compile-translations 命令）
bench --site <site> build --app <app>
```

验证：
```python
frappe.local.lang = "zh"
frappe._("Label Print")     # 应返回「标签打印」
```

⚠️ **用户个人的语言偏好会覆盖 `System Settings.language`** —— 
如果编译了但仍显示英文，先查用户的 language 设置。

⚠️ `bench build --app` 不编译翻译时，`assets/locale/<lang>/LC_MESSAGES/<app>.mo` 不会更新。

---

## 10. 容易踩的坑

1. **`fieldtype: "Virtual"` 不存在** → 报 `Field Type cannot be "Virtual"`。
   Virtual 是 `is_virtual` 这个 Check 属性，不是 fieldtype。
   且标准字段不能设 `is_virtual=1`（源码明确拒绝）。

2. **`is_virtual=1` 的值不持久化** → 每次加载都要重新计算，
   不是「存一份只读数据」。

3. **Property Setter 必填 `doctype_or_field`** → 不填报
   `[Property Setter, X]: doctype_or_field`。

4. **Customize Form 改不了 `fieldname`** → 主键不可改，
   要改名必须写 patch 做 `ALTER TABLE`。

5. **改 `fieldtype` 有 DB 副作用** → 涉及列类型变更，
   白名单里虽有 `fieldtype` 但生产环境先在测试站点验证。

6. **Client Script 的 `fieldname` 回调写错不报错** →
   只是永远不触发，静默失效。

7. **Custom Field 保存会自动清缓存，DocType JSON 改动不会** →
   后者需要 `bench migrate`。

8. **`in_list_view` / `in_standard_filter` 默认都是 0** →
   「字段建了但列表页看不到」是这个默认值造成的，
   不是 bug，改 flag 即可。

9. **DocType 名称翻译需要编译，且用户语言偏好优先** →
   `bench --site build --app` + 查用户 language。

10. **`frappe.clear_cache` 管不到 boot payload** →
    改了 hook / Dock 后浏览器仍显示旧状态时，
    要 flush Redis（见主 SKILL pitfall 63）。

---

## 相关文件

- 主 SKILL：`references/frappe-metadata-navigation.md` — 可见性 flag 速查与强制流程
- 主 SKILL：`references/workspace-content-blocks.md` — Workspace content block 形状
- 主 SKILL：`references/custom-app-packaging.md` — 自定义 app 的打包与注册