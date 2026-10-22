# 01_NrpNext — 二手跨国贸易管理系统

基于 **ERPNext v16.52.0** 的二次开发，用于「日本中古采购 → 拆解 → 跨境运输 → 国内销售」全流程管理。

## 业务链路

```
日本采购（Yahoo Auction / HardOff / ReRe / 线下店）
   ↓ 采购单 + 领收书 + 图片
拆解（整机 → CPU / 内存 / 主板 / 显卡 / 存储 / 电源 / 机箱）
   ↓ 成本按采购时参考价权重分摊到零件
同类合并运输（多台机器的同类零件打包）
   ↓ 物流批次录入，自动分摊到零件
报关（分解报关，多商品混装）
   ↓
香港中转 → 深圳 → 北京（BJ-CSRH）
   ↓
闲鱼（GOOFISH）销售
```

## 核心设计

| 概念 | 说明 |
|------|------|
| **成本模型** | 原始采购成本（永久锁定）+ 退税调整（可追加）；CNY 为真实成本，日元原价仅作参考 |
| **分摊算法** | 按「采购时参考价」权重分摊；PSU / 机箱等日本境内处理件可手动覆盖 |
| **三价格** | 采购成本 · 采购时参考价（永久保留）· 当前行情价（分类批量更新，走势图） |
| **编号规则** | 拆解单 `YYMMDD-NN`，零件 SN `YYMMDD-NN-{TYPE}-NN`（例 `261003-01-CPU-01`） |
| **退税四态** | 已完成 / 待举证（有领收书）· 待判定（无领收书）· 个人卖家 |
| **库存三态** | 在途（在途库存）· 可售（销售仓）· 自用（公司留用仓） |
| **资金成本** | 年化 8%，用于资金占用测算 |

## 目录结构

```
01_NrpNext/
├── app/secondtrade/              ERPNext app 源码
│   └── secondtrade/
│       ├── hooks.py
│       ├── patches.txt
│       ├── trade/                 模块（DocType 所在）
│       │   └── doctype/           13 个 DocType
│       ├── patches/v1_0/          数据迁移脚本
│       └── utils/                 成本分摊 / 标签生成
├── docs/开发规范.md               字段设计与报表设计
└── deploy/运维手册.md             莱卡云运维（备份/恢复/常用命令）
```

## DocType 一览

| DocType | 用途 | 编号前缀 |
|---------|------|---------|
| `Disassembly Note` | 拆解单（核心）：整机 → 零件 + 成本分摊 | `DIS-` |
| `Logistics Batch` | 物流批次：运费录入 + 自动分摊 | `BATCH-` |
| `Customs Declaration` | 报关单：分解报关 + 凭证 + 到岸 | `CUSTOMS-` |
| `Item Transit Record` | 商品轨迹：货运 / 携带 / 往返 | `TRANSIT-` |
| `Market Price History` | 行情价历史（走势图数据源） | `MP-` |
| `Evidence Package` | 整机退税证据包生成记录 | `EVID-` |
| `Trade Settings` | 贸易配置（单例）：资金成本率等 | — |

## 生产环境

| 项 | 值 |
|----|---|
| 服务器 | `110.42.60.173`（莱卡云） |
| 部署 | frappe_docker官方 compose |
| 站点 | `erp.motitoo.com` |
| ERPNext | v16.52.0 / Frappe v16.52.0 |
| 数据库 | MariaDB 11.8 |
| 备份 | 每日 03:17，保留 14 天 |

详见 `deploy/运维手册.md`。

## 部署方式

```bash
# 1. 传到服务器
scp -r app/secondtrade root@110.42.60.173:/opt/erp/staging/

# 2. 传入容器（容器内路径固定）
docker exec --user root frappe_docker-backend-1 rm -rf /home/frappe/frappe-bench/apps/secondtrade
tar -C /opt/erp/staging/secondtrade -cf - . | \
  docker exec -i --user root frappe_docker-backend-1 bash -c \
  'mkdir -p /home/frappe/frappe-bench/apps/secondtrade && \
   tar -C /home/frappe/frappe-bench/apps/secondtrade -xf - && \
   chown -R frappe:root /home/frappe/frappe-bench/apps/secondtrade'

# 3. pip 安装
docker exec --user root frappe_docker-backend-1 bash -c \
  'cd /home/frappe/frappe-bench/apps/secondtrade && \
   /home/frappe/frappe-bench/env/bin/pip install -e .'

# 4. 注册 + migrate
docker cp /opt/erp/staging/secondtrade/secondtrade/patches.txt \
  frappe_docker-backend-1:/home/frappe/frappe-bench/sites/apps.txt   # 追加 secondtrade
docker exec frappe_docker-backend-1 bash -c \
  'cd /home/frappe/frappe-bench && bench --site erp.motitoo.com migrate'

# 5. 备份
/usr/local/bin/frappe-backup.sh
```

## ⚠️ Frappe v16 开发约定（踩坑记录）

这几个约定是本项目最大的坑，改代码前务必确认：

### 1. DocType 目录与文件命名

```
✅ secondtrade/trade/doctype/disassembly_note/disassembly_note.json
❌ secondtrade/trade/doctype/disassembly_note/Disassembly Note.json      # 带空格
❌ secondtrade/secondtrade/doctype/...                                    # 多套一层
❌ secondtrade/trade/doctype/disassembly_note/Disassembly Note/*.json    # 多套一层
```

Frappe 要求**扁平结构 + 小写下划线命名**，且每个目录（含 `doctype/`、`trade/`）都必须有 `__init__.py`。

### 2. 模块名不能与 app 同名

Frappe 拼导入路径的逻辑：

```python
# frappe/modules/utils.py
def get_module_name(doctype, module, ...):
    return f"{app}.{module}.doctype.{doctype}.{doctype}"
```

- app 名 = `secondtrade`（Python 包 = `apps/secondtrade/secondtrade/`）
- 模块名 = `trade`（目录 = `apps/secondtrade/secondtrade/trade/`）
- 完整导入路径 = `secondtrade.trade.doctype.disassembly_note.disassembly_note`

**踩过的坑**：模块名曾用 `Secondtrade`（与 app 同名 → 双层）、`core`（与 Frappe 内置 `Core` 冲突 → 主键重复）。最终定为 `trade`。

同时 `tabModule Def` 表里的模块名必须**全小写**，否则 `load_doctype_module` 找不到路径。

### 3. 不要手写 `states`

```json
❌ "states": [{"name": "__Draft", "doc_status": 0}, ...]
❌ "states": [{"name": "Draft", "doc_status": 0}, ...]
✅ 省略 states，让 Frappe 用默认值
```

`tabDocType State` 的主键**只有 `name` 一列**（没有 `parent`），全局唯一。手写 `__Draft` / `Draft` 都会和已有 DocType 撞主键。省略后 Frappe 会自动生成 hash 命名的默认状态。

### 4. `patches.txt` 必须放 `post_model_sync`

```ini
[pre_model_sync]
# 数据 patch 放这里会在 DocType 表创建之前执行 → 表不存在 → 静默失败

[post_model_sync]
secondtrade.patches.v1_0.create_custom_fields
secondtrade.patches.v1_0.create_item_groups
secondtrade.patches.v1_0.create_warehouses
secondtrade.patches.v1_0.create_trade_settings
secondtrade.patches.v1_0.set_role_permissions
```

**踩过的坑**：品类 patch 放在 `pre_model_sync`，执行时 `tabItem Group` 表还不存在，只建了 2 个就中断，且报错被 migrate 的进度条淹没。

### 5. Link 字段默认值要用完整 DocType name

```json
✅ "default": "JP-ISTK - ISTK"          // Warehouse.name（v16 自动拼公司后缀）
❌ "default": "JP-ISTK"                // warehouse_name，不是 name
❌ "default": "JP-ISTK - ISOTENKAI"    // 公司简称取自根仓库「所有仓库 - ISTK」
```

v16 的 `Warehouse.name` = `warehouse_name - 公司简称`，公司简称来自根仓库名（如 `所有仓库 - ISTK` → `ISTK`，不是 Company.name `ISOTENKAI`）。

存在性检查也要用字段而非 name：

```python
frappe.db.exists("Warehouse", {"warehouse_name": "BJ-CSRH", "company": "CSRH"})  # ✅
frappe.db.exists("Warehouse", "BJ-CSRH")                                        # ❌
```

### 6. 多级 Link 的 name 由系统拼接

`Item Group` 的多级 name 形如 `二手电脑硬件 - 内存 - DDR4`，**无法预先推断**。创建时要逐层反查：

```python
doc = frappe.get_doc({"doctype": "Item Group", "item_group_name": "DDR4",
                       "parent_item_group": parent_real_name, "is_group": 1})
doc.insert()
resolved["DDR4"] = doc.name   # 用 doc.name 传给下一层
```

传 `"二手电脑硬件/内存"` 这种斜杠路径会报 `LinkValidationError`。

### 7. patch 幂等性

所有 patch 必须可重复执行（migrate 可能重跑）：

```python
# ✅ upsert 而非 insert
if frappe.db.exists("Warehouse", {"warehouse_name": name, "company": company}):
    frappe.db.set_value("Warehouse", wh_name, values, update_modified=False)
else:
    frappe.get_doc(...).insert(ignore_permissions=True)
```

---

**版本**：v1.0
**最后更新**：2026-10-22
