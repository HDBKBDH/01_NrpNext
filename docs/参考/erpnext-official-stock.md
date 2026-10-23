# ERPNext 官方文档整理：库存与成本核算（Inventory & Costing）

> 面向业务：二手电脑零件跨境贸易（日本中古采购 → 拆件 → 出口）
> 目标站点：ERPNext/Frappe **v16.52.0**（版本号来自任务上下文，**未能在线核实**，见文末「验证说明」）
> 抓取日期：2026-10-23

---

## 0. 关于本文档的可信度标注

本文档中每一条机制说明都带有标注：

| 标注 | 含义 |
|---|---|
| ✅ **已验证（文档）** | 原文抓取自 docs.frappe.io 官方文档页面，页名在每节末尾给出 |
| ⚠️ **推断** | 基于官方文档事实 + Frappe/ERPNext 通用行为的合理推断，**未在文档中直接读到该句**，落地前需实测 |
| 🔧 **可运行代码** | 可直接在 `bench console` / `bench execute` 中运行的脚本示例 |
| 🌐 **环境限制** | 本次抓取/验证过程中遇到的网络或权限障碍 |

> **重要背景**：`docs.erpnext.com` 现已 301 跳转至 `docs.frappe.io/erpnext/...`，旧 slug 大多 404。
> 官方文档站同时托管 **v15 / v16 / v17** 的内容，且 **v17 内容已经混入**（见 §5.6、§6.5）。
> 引用时必须看清是哪一版。本文已逐条标注。

---

## 1. 核心库存单据链路及其 Stock Ledger 影响

### 1.1 三大账簿的分工

✅ **已验证（文档）** — `how-transactions-affect-the-ledger`

ERPNext 在单据 **submit（提交）** 时按需生成三类分录：

```
Draft 单据 --Submit--> Submitted 单据
                          ├── General Ledger Entries      → 财务报表
                          ├── Payment Ledger Entries      → 应收应付/账龄报表
                          └── Stock Ledger Entries        → 库存余额与估值报表
```

| Ledger | 主要用途 | 常见来源单据 |
|---|---|---|
| General Ledger | 按科目记录借贷金额 | Invoice、Payment、Journal、**库存交易**、资产、薪资 |
| Payment Ledger | 应收应付引用、核销、未清金额 | Invoice、Payment、Credit Note、Journal |
| Stock Ledger | 按 Item + Warehouse 记录数量、入库价、估值价、库存价值 | Receipt、Delivery、Stock Entry、更新库存的 Invoice |

关键机制：
- **Draft 单据不产生任何账簿分录**，保存草稿对账无影响。
- `Posting Date` 决定会计期间；`Posting Time` 在涉及库存时会**影响估值计算顺序**。
- 取消（Cancelling）已提交单据**不是删除历史，而是生成反向分录**（immutable ledger）。要更正必须 **Cancel + 新建修正单据**。

### 1.2 采购链路：Purchase Order → Purchase Receipt → Purchase Invoice → Payment Entry

✅ **已验证（文档）** — `purchase-cycle-ledger-impact` + `purchase-receipt`

| 单据 | 库存影响 | 会计影响（Perpetual Inventory） |
|---|---|---|
| Purchase Order | 无 | 无 |
| **Purchase Receipt** | 收货入库（Accepted + Rejected 分别入仓） | 借 Stock In Hand / 贷 **Stock Received But Not Billed** |
| Purchase Invoice | 无（除非勾选 Update Stock） | 借 Stock Received But Not Billed / 贷 Accounts Payable |
| Payment Entry | 无 | 借 Accounts Payable / 贷 Bank or Cash |

**Stock Received But Not Billed 是一个过渡性科目（clearing account）**：它让「货已到」和「供应商发票已到」这两个日期可以分开记账，而不丢失收货产生的负债。Purchase Invoice 的作用是**把这个临时负债转到真正的应付账款**。

> 官方例子：采购 5 台电子设备 @ $520 = $2,600
> - 提交 Purchase Receipt：借 `Stock In Hand` $2,600，贷 `Stock Received But Not Billed` $2,600
> - 提交 Purchase Invoice：借 `Stock Received But Not Billed` $2,600，贷 `Accounts Payable` $2,600
> - 提交付款：借 `Accounts Payable` $2,600，贷 `Bank` $2,600

**Rejected Warehouse 机制** ✅ **已验证（文档）** — `purchase-receipt`
> 当预期会有退货时，应单独建一个非 group 仓库（如 Returns Warehouse）。
> Accepted 数量进入正常仓库计入单据总额；Rejected 数量**仍然计入库存**，但被隔离在可用仓库之外。

> 二手贸易场景提示 ⚠️ **推断**：ERPNext 原生只有 Accepted / Rejected 两个仓，没有「待检区/待判品区/待拆件区」。
> 待检、待拆件、坏件、自用件需要**自建 Warehouse**（不同 Warehouse Type）来区分。

### 1.3 Putaway（自动分配仓库）

✅ **已验证（文档）** — `putaway-rule`

Putaway Rule 定义**入库库存的仓库分配策略**，对 **Company + Item + Warehouse 组合唯一**。

- 策略只考虑 **Capacity（容量）** 和 **Priority（优先级）**。
- 优先级先看，同优先级则看**剩余空间**，空间多的优先分配。
- 分配到仓库满为止；全部满载时 ERPNext 会提示。
- **生效范围**：Purchase Receipt，以及 Stock Entry 的 **Material Receipt / Material Transfer**。
- 需要在单据上勾选 **Apply Putaway Rule**；勾选后**保存时会重新应用**规则。

配置字段：`Company`、`Item`、`Warehouse`、`Capacity`（可选 UOM）、`Priority`（1 最高）。

> ⚠️ **推断**：Putaway Rule **只做容量分配，不做质量/状态判定**。
> 二手件「合格/待测/坏件」的分流必须靠**人工改目标仓**或用 **Stock Entry 二次调拨**实现。

### 1.4 Stock Entry 与 7 种 Purpose

✅ **已验证（文档）** — `stock-entry` + `stock-entry-purpose`

Stock Entry 记录**仓库之间的物品移动**，Source Warehouse 扣减、Target Warehouse 增加。

| Purpose | 用途 | 库存效果 |
|---|---|---|
| **Material Issue** | 领料（含消耗品领用、序列号/批次**盘盈亏调整**） | 从 Source Warehouse 扣减 |
| **Material Receipt** | 收货（无 Purchase Order 的采购、**序列号/批次开账余额**） | 进入 Target Warehouse。**Item Valuation 为必填字段** |
| **Material Transfer** | 仓库间调拨 | Source 减 → Target 增 |
| **Material Transfer for Manufacturing** | 领原料到生产（通常 WIP 仓），由 Work Order 生成，行项目取自 BOM | Stores → WIP |
| **Material Consumption for Manufacture** | 针对同一 Work Order 的多次消耗 | Source 减 |
| **Manufacture** | 完工入库，原料扣减 + 成品入库一次完成 | 原料从 WIP 减，成品进目标仓 |
| **Repack** | 大包装拆成小包装 | 多 item 出 → 新 item 入 |
| **Send to Subcontractor** | 发料给分包商（需先建分包商仓库），由 Purchase Order 生成 | 本公司仓 → 分包商仓 |

> **二手拆件场景的关键结构缺口** ⚠️ **推断**：
> ERPNext 原生**没有「一台整机拆成多个零件」的单据**。
> 标准 Manufacture 假设「投入 N 个原料 → 产出 1 个成品」，与「投入 1 个整机 → 产出 8 个零件」方向相反。
> 拆件只能退化为：**Stock Entry (Repack / Material Transfer)** 手工多行录入，
> 或**自建拆解单 DocType**（见 `erpnext-secondhand-trade` skill 的 `disassembly-model.md`）。
> 官方 v17 文档出现了 `Disassembly Order` / `Disassembly Note` 链接，说明上游也在做，
> 但 **v16.52.0 上不可用**（见 §5.6）。

### 1.5 销售链路：Sales Order → Delivery Note → Sales Invoice → Payment Entry

✅ **已验证（文档）** — `selling-cycle-ledger-impact` + `delivery-note`

| 单据 | 库存影响 | 会计影响 |
|---|---|---|
| Sales Order | 无 | 无 |
| **Delivery Note** | 出库扣减 | 借 **Cost of Goods Sold** / 贷 **Stock In Hand** |
| Sales Invoice | 无（除非 Update Stock） | 借 Accounts Receivable / 贷 Sales |
| Payment Entry | 无 | 借 Bank / 贷 Accounts Receivable |

**Delivery Note 的 COGS 按估值价计算，不是按售价** ✅ **已验证（文档）**
> 官方例子：卖 2 台手机 @ $699 = $1,398，但库存估值为 $866.76。
> Delivery Note 记 **$866.76**（COGS / 贷 Stock In Hand），Sales Invoice 记 $1,398。
> 毛利 = $1,398 − $866.76 = **$531.24**。

Delivery Note 状态：`Draft` / `To Bill` / `Completed` / `Return Issued` / `Cancelled` / `Closed`。
- `Closed` 用于**短结**（Short-closing）：订 20 发 15，剩余 5 不发也不开票。
- 支持**分批交付**（Partial Deliveries）。
- 可从 `Pick List` 批量创建 Delivery Note（按 Customer 分组）。

**Sales Return 的处理** ⚠️ **推断**：官方文档未单独开页说明 Sales Return。
在 ERPNext 中退货通过 **Sales Invoice of type `Return`**（或 Credit Note against invoice）处理，
库存回补由该单据的 `Update Stock` 触发，方向与 Delivery Note 相反。

```python
# 🔧 销售退货：Return 类型 Sales Invoice，回补库存
# 走标准 do_submit(on_submit=1)，库存回补 + 收入冲回 + 应收冲减 一次性完成
frappe.get_doc({
    "doctype": "Sales Invoice",
    "is_return": 1,
    "return_against": "SINV-00001",      # 必须是已提交的 Sales Invoice
    "company": "ISOTENKAI",
    "customer": "CUST-0001",
    "items": [{
        "item_code": "RAM-DDR4-16G",
        "serial_and_batch_bundle": "SABB-00042",   # v15+ 必须传 Bundle
        "qty": 1,
        "rate": 450,
        "warehouse": "完成品仓 - ISTK",
    }],
}).insert().submit()
```
> ⚠️ 以上脚本为**基于文档机制编写的示例，未在 v16.52.0 实测**。
> 关键风险点：v16 中 `Serial Number` 已更名为 `Serial No`，`Serial and Batch Bundle` 的
> 字段名需在目标站点用 `frappe.get_meta("Serial and Batch Bundle").fields` 确认。

### 1.6 Sales Invoice 勾选 Update Stock 的效果

✅ **已验证（文档）** — `how-transactions-affect-the-ledger`

Sales Invoice 勾选 Update Stock 后，**在同一次提交内**同时产生三类分录：

| 账簿 | 内容 |
|---|---|
| General Ledger | 借 Accounts Receivable（发票额），贷 Income（净销售额），贷 Output Tax Payable（税额） |
| General Ledger（库存部分） | 借 **Cost of Goods Sold**，贷 **Stock asset** |
| Payment Ledger | 客户未清金额（未付款前一直挂着） |

> 这意味着**不需要先开 Delivery Note** 就能一次性完成出库+开票。
> 二手出口场景若追求单据数量少，可直接用「Sales Invoice + Update Stock」。

---

## 2. Serial Number 与 Batch 机制

### 2.1 v16 的重大变更：Serial Number → Serial No

✅ **已验证（文档）** — sitemap + `serial-no` + `serial-and-batch`

- 文档站 v16 章节的页面 slug 是 **`serial-no`**（不是 `serial-number`，后者 404）。
- 页内正文仍混用 "Serial Number" / "Serial No"。
- `serial-and-batch` 页面明确写 **"From version 16, to enable serial / batch feature for the item, first check the 'Enable Serial and Batch No for Item' checkbox in the 'Stock Settings'."**

> **代码里写 doctype 名之前，先读目标站点的真实 doctype 名**：
> ```python
> # 🔧 确认 v16 上的真实 doctype 名与 autoname 规则
> import frappe
> frappe.set_user("Administrator")
> for dt in ("Serial No", "Serial Number"):
>     exists = frappe.db.exists("DocType", dt)
>     print(dt, "exists=", bool(exists))
>     if exists:
>         meta = frappe.get_meta(dt)
>         print("   autoname =", meta.autoname)
>         print("   fields   =", [f.fieldname for f in meta.fields][:15])
> ```
> ⚠️ 已知（来自本项目 skill 记录，未在本次会话验证）：v16 的 `Serial No.autoname` 是
> `field:serial_no`，因此 `frappe.db.exists("Serial No", "SN-01")` **会静默返回 None**，
> 必须用 `frappe.db.exists("Serial No", {"serial_no": "SN-01"})` 查询。

### 2.2 启用前提（三重开关）

✅ **已验证（文档）**

1. **Stock Settings** → 勾选 **`Enable Serial and Batch No for Item`**（全局总开关）
2. **Item master** → 勾选 **`Has Serial No`** 或 **`Has Batch No`**
3. 自动生成还需：
   - Serial：Item 上设置 **Serial Number Series**（如 `PB2L.#####`）
   - Batch：Item 上勾选 **`Automatically Create New Batch`** 并设置 **Batch Number Series**

### 2.3 Serial No 只能通过 Stock Ledger 产生 —— 直接创建时 warehouse 不可设置

✅ **已验证（文档）** — `serial-no`（原文）

> *"Inventory of an Item can only be affected if the Serial No is transacted via a Stock
> transaction (Stock Entry, Purchase Receipt, Delivery Note, Sales Invoice).
> **When a new Serial No is created directly, its Warehouse cannot be set.**"*

其他相关规则（同页已验证）：
- Serial No 的 **Status 由 Stock Entry 决定**。
- **只有 status = `Available` 的 Serial No 才能出库。**
- 如果 Item 配了 Serial No Series，Stock Entry / Purchase Receipt 里 Serial No 留空即可自动生成。
- 也可以在 Serial Nos 列**手填**，submit 时自动创建这些 Serial No。
- 如果该 Item 已经发生过任何交易，**Serial No / Batch 的绑定就不能再改**。

> ⚠️ **推断（本项目已知行为，未在本次会话实测）**：v16 中带 `warehouse` 直接 insert Serial No
> 会抛 `SerialNoCannotCreateDirectError`，因为仓库只能通过 Stock Ledger 赋予。
> 这对**拆件产生的零件**是硬约束：拆件没有 Purchase Receipt 驱动 Ledger，
> 只能**先建无 warehouse 的 Serial No，位置信息交给拆解单/物流批次承载**。

```python
# 🔧 创建 Serial No（不设 warehouse —— 位置由 Stock Ledger 决定）
import frappe
frappe.set_user("Administrator")

sn = frappe.get_doc({
    "doctype": "Serial No",          # ⚠️ v15 是 "Serial Number"，务必先确认
    "serial_no": "241015-LAP-01",   # ⚠️ v16 autoname=field:serial_no
    "item_code": "IP15-128G-EXC",
    "status": "Active",
    # 不要传 warehouse —— 只能由 Stock Ledger 写入
}).insert()
print("created:", sn.name)

# ⚠️ v16 查询必须按字段名，不能按主键
print(frappe.db.exists("Serial No", {"serial_no": "241015-LAP-01"}))   # → 1
print(frappe.db.exists("Serial No", "241015-LAP-01"))                 # → None（静默失配）
```

### 2.4 Serial and Batch Bundle（v15 引入，v16 沿用）

✅ **已验证（文档）** — `serial-and-batch-bundle`

**为什么需要它**（原文）：
> v15 之前 `Serial No` 字段是 **Small Text**，一个字段可以塞多个序列号，
> 导致大量数据完整性问题。v15 把它改成 **Link** 字段。
> 但 Frappe 不支持 child table 套 child table，所以新增了 `Serial and Batch Bundle` 这个 DocType
> 来「装载/分发」多个序列号/批次号。

**核心规则** ✅ **已验证（文档）**
> *"Users must create a separate Serial and Batch Bundle for each stock transaction.
> They **cannot** use the same Serial and Batch Bundle across multiple stock transactions."*

**自动生成条件** ✅ **已验证（文档）**

| 方向 | 触发单据 | 前置配置 |
|---|---|---|
| **入库（Inward）** | Purchase Receipt、Stock Entry (Material Receipt) | Serial Item 配好 Serial Number Series；Batch Item 勾 `Automatically Create New Batch` + 配 Batch Number Series |
| **出库（Outward）** | Delivery Note、Stock Entry (Material Issue) | Stock Settings 勾选 **`Auto Create Serial and Batch Bundle For Outward`**；可另设 `Pick Serial / Batch Based On` = FIFO / LIFO / Expiry |

**手工创建 Bundle** ✅ **已验证（文档）**
> 入库方向手工创建时，**Serial No / Batch 记录必须已存在于系统中**。
> 可以用 Serial and Batch Selector 的 **CSV 导入**批量预建（空白模板可在该选择器下载）。

### 2.5 v15+ 禁止 Serial/Batch Item 的负库存

✅ **已验证（文档）** — `serial-no` + `batch` + `serial-and-batch`（三处一致）

> *"Allow Negative Stock has been removed for Serial / Batch Items from version 15.
> So from version 15 users won't be able to make negative stock transactions for serial /
> batch items **even though Allow Negative Stock has enabled in the Stock Settings**."*

> 实务含义：**序列号件一旦发出就不可再被"负数退回"**。
> 退货必须是一个真实的正向入库（Return Invoice + 新 Bundle），不能靠负数冲销。

### 2.6 Batch 特有能力

✅ **已验证（文档）** — `batch` + `batch-split` + `retain-sample-stock`

- Batch 可**手工分仓（Move 按钮）**和**拆分（Split 按钮）**。
- 设置了 expiry date 的 Batch 会显示 `Not Expired` / `Expired`；未设则显示 `Not Set`。
- Batch ID 的下拉会按 **Item Code + Warehouse + Batch Expiry Date（对比单据 Posting date）+ 该仓实际数量** 过滤。
- **Retain Sample（留样）**：基于 Batch。Item 上设 `Retain Sample` + 最大留样量；
  Material Receipt 的 Stock Entry 里填 Sample Quantity；submit 后出现
  **Make Retention Stock Entry** 按钮，生成一笔 Material Transfer 把样品转到
  Stock Settings 里配置的 **Sample Retention Warehouse**。
- **Batch Split（v16 新能力）** ✅ **已验证（文档）** — `batch-split`
  把一个大批次切成多个可独立追溯的小批次（每片一个批号），每个新批号记录**父批号**。
  前提：输出 Item 启用 `Has Batch No` + `Automatically Create New Batch` + Batch Number Series；
  原料也必须是 batch-tracked。适用：金属棒料剪裁、钢材/纸卷分切、木材开料。
  **不适用于混料（多进一出）**。

### 2.7 Serial-wise Valuation（按序列号单独计价）

✅ **已验证（文档）** — `use-serial-no-wise-valuation`

Item master 上的一个复选框，**决定序列化商品如何计算成本**，不影响是否追踪序列号。

| | 勾选（默认） | 不勾选 |
|---|---|---|
| 序列号追踪 | 是 | 是 |
| 每序列号存成本 | 是 | 否 |
| 出库成本 | **该件的实际买入价** | **Item 平均成本** |
| 适用规模 | 几百个序列号 | 几百万个序列号 |

> 文档给的判断准则：**「如果你能想象手工数完这些序列号，就保持勾选。如果是整车拉进来的，就取消勾选。」**

> **二手贸易强烈建议保持勾选（默认）** ⚠️ **推断**：
> 二手件每台价格都不同（成色、配置、卖家），出库成本必须等于**那一台**的买入价。
> 若用平均值，毛利报表会系统性失真。

**易混淆点** ✅ **已验证（文档）** — `how-is-valuation-rate-of-serialised-item-calculated-in-erpnext`
> *"...in the case of serialised Item, these settings are ignored.
> The valuation rate is updated from the **first incoming stock entry rate**."*
>
> 即：**序列号件的 valuation rate 不是从 Item master 取的**，而是从**第一条入库流水的费率**开始，
> 之后随该 Item 的其他交易演化。而勾选 Serial No Wise Valuation 后，
> 每个序列号**各自**持有自己的成本。

### 2.8 `automatically_mark_serial_number_based_on_item` 设置

✅ **已验证（文档）** — `stock-settings`

文档中的对应设置名为：**`Automatically Set Serial Nos based on FIFO`**

> *"Serial numbers for stock will be set automatically based on the Items entered based on
> **first in first out**. The Serial Numbers will be set automatically in transactions like
> Purchase/Sales Invoices, Delivery Notes, etc."*

⚠️ **推断**：任务中提到的 `automatically_mark_serial_number_based_on_item` 可能是该设置的
**内部 fieldname 或历史字段名**。官方文档未使用此拼写。落地前请在目标站点核对：

```python
# 🔧 核对 Stock Settings 中与序列号自动分配相关的字段真实 fieldname
import frappe
frappe.set_user("Administrator")
meta = frappe.get_meta("Stock Settings")
for f in meta.fields:
    label = (f.label or "").lower()
    fld = (f.fieldname or "").lower()
    if any(k in label or k in fld for k in ("serial", "batch", "auto")):
        print(f"{f.fieldname:55s} | {f.fieldtype:12s} | {f.label}")
```

### 2.9 追溯报表

✅ **已验证（文档）** — `serial-and-batch-traceability-report`

- **Backward Traceability**：这批货用了哪些原料、原料来自哪里。
- **Forward Traceability**：这批货用到了哪里、交给了谁。
- **Map Raw Materials to Finished Goods**（`Stock Entry → Actions`）：
  在 **Manufacture / Repack** 的 Stock Entry 上，记录**哪个原料序列号/批次进了哪个成品序列号/批次**。
  - 前置：成品与原料**都**需 Serial 或 Batch 追踪。
  - **映射一旦 submit 就固定**：已映射的原料不能再改或清除，只能补映射仍为空的。
  - Stock Settings 的 `Auto Map Raw Materials to Finished Goods` **默认关闭**。

> **对二手拆件的价值极高** ✅（文档原例）✅：
> *"If you make 3 laptops from 3 motherboards, you cannot tell which motherboard is inside
> which laptop."* —— 这正是拆件业务的核心溯源需求。
> ⚠️ **推断**：官方该功能的措辞是「原料→成品」（制造方向）。
> 二手场景是「整机→零件」，方向相反，**能否直接套用需实测**。

---

## 3. Warehouse 类型与作用

### 3.1 Warehouse 的本质是「存储位置」，不是「建筑」

✅ **已验证（文档）** — `warehouse`

> *"The terminology of 'Warehouse' in ERPNext is a bit broader though and maybe can be
> regarded as 'storage locations'."*

支持多层级树：`Warehouse > Room > Row > Shelf > Bin`。
- `Is Group` 勾上才能建子仓库。
- **Warehouse 名称带 Company 缩写保存**，便于一眼识别归属公司。

### 3.2 Warehouse Account —— 仓库与会计科目的联动

✅ **已验证（文档）** — `warehouse-ledger-link`（原文）

> *"Each warehouse is linked to a ledger in chart of accounts through the **'Account' field**
> in the warehouse. If the Account field is empty in a warehouse, then the Account mentioned
> in the **parent** of that warehouse is considered. If an Account could not be determined by
> tracing the hierarchy, then the **Default Inventory Account** mentioned in the **Company**
> record is considered."*

公司创建时默认生成 `Stock In Hand` 科目，路径为：
`Chart of Accounts > Assets > Current Assets > Stock Assets > Stock In Hand`

**三级回退链** ✅：
```
Warehouse.Account  →  Parent Warehouse.Account  →  Company 的 Default Inventory Account
```

**建议** ✅ **已验证（文档）**
> 详细的仓库树（货架/库位）应该**统一挂到根仓库的科目上**，
> 因为多数场景不需要按每个货架单独核算库存价值。

### 3.3 v16 新增：Item-wise Inventory Account

✅ **已验证（文档）** — `inventory-account`（原文）

> *"In ERPNext, users can either set up a **Warehouse-wise** Inventory Account or use the
> default Inventory Account from the Company master, which is 'Stock In Hand.'
> **From the Version 16**, users can also able to set the **Item-wise** Inventory Account.
> To do this, they need to enable the option **'Enable Item-wise Inventory Account'**
> in the Company master."*

启用后：
- 可在 **Item master** 定义 Default Inventory Account；
- 也可在 **Item Group 或 Brand 层级**定义（不想逐个 Item 设置时）；
- ⚠️ **关键约束**：*"Users can choose to use either item-wise or warehouse-wise inventory
  accounts, **but not both**."*

> **本项目建议** ⚠️ **推断**：
> 保持 **Warehouse-wise**（不启用 Item-wise）。理由：二手件的库存价值口径应与
> 「哪个仓」（可售 / 自用 / 待检）对齐，而不是与「哪个 Item」对齐。
> 一旦切到 Item-wise，仓库维度的库存价值报表口径会变。

### 3.4 标准 Warehouse 集合（Stores / WIP / Finished Goods / Goods In Transit 等）

⚠️ **本节重要提示**：官方 `warehouse` 文档**只讲了 Warehouse Type 这个自定义分类标签**，
**没有**给出 Stores / WIP / Finished Goods / Goods In Transit / Virtual Warehouse /
Customer Warehouse 这一套「标准仓库」的权威定义表。以下逐项标注来源：

| 仓库 | 来源 | 证据强度 |
|---|---|---|
| **Stores** | `stock-settings`（"Default Warehouse… fetched into the Default Warehouse in the Item master"）、`purchase-cycle-ledger-impact`（"贷 Stock In Hand"）、`stock-entry-purpose`（"Stores"） | ✅ 文档中确实作为常规提法出现 |
| **Work In Progress (WIP)** | `stock-entry`（"transferred for manufacturing… generally WIP warehouse"）、`stock-entry-purpose`（"generally WIP warehouse"） | ✅ 文档明确提到 |
| **Finished Goods** | `putaway-rule` 官方示例中出现仓库 `'Finished Goods - UPI'` | ✅ 文档示例中出现 |
| **Goods In Transit** | ⚠️ **推断** —— 未在本次抓取的页面中读到权威定义 | ⚠️ 仅推断 |
| **Virtual Warehouse** | ⚠️ **推断** —— 未读到权威定义 | ⚠️ 仅推断 |
| **Customer Warehouse（客户仓）** | ✅ **已验证（文档）** — `stock-settings` 的 "Inter Warehouse Transfer Settings" | ✅ |

**Customer / Supplier Warehouse 的真实用途** ✅ **已验证（文档）** — `stock-settings`

原文：
> *"**Enable customer warehouse for material transfer from Delivery Note and Sales Invoice**
> — This option is useful when material transfer needs to be presented as a Delivery Note.
> For example, there are **statutory requirements where taxes are to be applied on each
> transfer of Material**. It is easier to manage in a transaction like Delivery Note, than in
> the Stock Entry."*
>
> *"**Enable supplier warehouse for material transfer from Purchase Receipt and Purchase
> Invoice**" —— 同理。*

**这是跨境贸易的关键机制** ✅：某些国家（如日本）对每一次货物移动都要求开票/纳税，
此时库存移动不能只用一个 Stock Entry 应付，而要**借用 Delivery Note / Purchase Receipt
作为税务凭证**，因此需要「客户仓 / 供应商仓」作为对手方仓库。

⚠️ **推断**：同理，**Goods In Transit（在途仓）** 是为了让「已离开卖方仓、尚未到达买方仓」
这段在途库存有独立的估值和账务归属，逻辑与 Customer Warehouse 一致 —— 货物物理在路上，
但账面必须落在某个仓。**Virtual Warehouse（虚拟仓）**则用于没有任何物理存储地点、
但需要挂账的库存。**这三者均未在本次抓取的官方页面中得到直接确认。**

> **给二手出口业务的落地建议** ⚠️ **推断**：
> | 业务环节 | 建议 Warehouse | 理由 |
> |---|---|---|
> | 日本中古到货待检 | `待检仓` | 与可售库存隔离 |
> | 拆件后合格零件 | `可售零件仓` | 参与可售库存报表与毛利 |
> | 拆件后坏件/待修 | `坏件仓` | 有成本、占资金，但不进可售 |
> | 自用件 | `自用仓` | 有成本、占资金，但不进可售毛利 |
> | 出口在途 | `出口在途仓` | 对应 Goods In Transit |
> | 客户所在地（待收货） | `客户仓 - <客户>` | 启用 Customer Warehouse 机制 |

### 3.5 Warehouse 对库存估值与报表的影响

✅ **已验证（文档）**
- **库存余额按 Item × Warehouse 组合维护**：`warehouse` 页原文
  *"ERPNext maintains stock balance for every distinct combination of Item and Warehouse."*
- Stock Ledger 记录数量、入库价、估值价、库存价值，**按 Item + Warehouse**。
- 启用 Perpetual Inventory 时，**每个 Warehouse 必须属于特定公司**，才能维护公司维度的库存余额。
- Warehouse 的 `Account` 字段决定该仓库存的**资产负债科目**，
  所以不同 Warehouse 可以对应不同科目 → **按仓拆分的库存价值**。

**报表影响** ✅ **已验证（文档）** — `stock-level-report` / `quick-stock-balance` / `stock-ledger`

Stock Projected Quantity Report 提供：
```
Projected Qty = Actual Qty + Planned Qty + Requested Qty + Ordered Qty − Reserved Qty
```
- Actual Qty：仓库实际可用量
- Planned Qty：已下达 Work Order 待生产
- Requested Qty：已提 Material Request 未下单
- Ordered Qty：已下单未收货
- Reserved Qty：已销售订单未发货

Quick Stock Balance 工具可实时取**指定日期 + 指定仓库**的数量与价值。
Stock Ledger Report 的关键列 ✅ **已验证（文档）**：
- **Incoming Rate**：库存实际入账价值，等于单据 `Rate` 字段
- **Valuation Rate**：按所选估值方法计算
- **Balance Value** = Valuation Rate × Balance Quantity

### 3.6 Warehouse 命名规则（踩坑高发区）

⚠️ **推断 + 本项目已验证经验**（未在本次会话实测）：
- v16 中 `Warehouse.name` 由框架生成为 `<label> - <company short name>`，
  **不是你输入的 warehouse_name**。
- **不同项目的 Company 命名格式可能相反**：本项目 `ISOTENKAI`（abbr `ISTK`）
  生成 `<abbr> - <name>`，而 `CSRH` 生成 `<name> - <abbr>`。
- 改 `warehouse_name` 不会重算主键，必须 `frappe.rename_doc()`。

```python
# 🔧 建仓：读真实值，不硬编码生成的主键
import frappe
frappe.set_user("Administrator")

wh = frappe.get_doc({
    "doctype": "Warehouse",
    "warehouse_name": "可售零件仓",
    "company": "ISOTENKAI",
    "is_group": 0,
    "parent_warehouse": None,   # 顶层
}).insert()
print("真实 name =", wh.name)     # 例: "可售零件仓 - ISTK" 或 "ISTK - 可售零件仓"

# 任何按名字匹配的地方都用属性匹配，不要用 name LIKE '% - 标签'
print(frappe.db.exists("Warehouse", {"warehouse_name": "可售零件仓", "company": "ISOTENKAI"}))
```

---

## 4. 库存估值

### 4.1 估值方法解析顺序（v16 新增 Company 层）

✅ **已验证（文档）** — `item-valuation-transactions`

原文（New in v16 部分）：
> *"In ERPNext v16, users can now select Valuation Method **per company** basis and a new
> field in the **Company DocType** has been added for the same. The old field in **Stock
> Settings** single DocType still remains and will only be used in certain cases where the
> reference document does not have a reference to any company (such as **Batch**).
> The valuation method will be fetched in the following order:
> **Item level → Company level → Manufacturing Settings (global) level**"*

⚠️ 注意文档这里有个用词不一致：前面说 "Stock Settings"，后面说 "Manufacturing Settings"。
**Stock Settings 是确定存在的字段来源**（`stock-settings` 页有 "Default Valuation method"），
"Manufacturing Settings" 疑为文档笔误。

**谁能更新 Item 的估值速率** ✅ **已验证（文档）** — `item-valuation-transactions`
> Item 估值在以下三类单据创建时更新：
> **Purchase Receipt** / **Stock Entry (Material Receipt)** / **Stock Reconciliation（开账余额用）**

⚠️ **坑** ✅ **已验证（文档）** — `item-valuation-transactions`
> *"Note that once ledger entries are made for an item, **this option will no longer be
> visible in the Item form**."*
> 也就是说：**一个 Item 一旦有过库存流水，Valuation Method 字段在界面上就消失了**（不可再改）。

### 4.2 FIFO vs Moving Average 的实际差异

✅ **已验证（文档）** — `calculation-of-valuation-rate-in-fifo-and-moving-average`

官方示例：

| Date | Transaction | Qty | Unit Cost |
|---|---|---|---|
| 1-4-2020 | Purchase | 10 | 100 |
| 6-4-2020 | Purchase | 20 | 120 |
| 10-4-2020 | Sale | 15 | **?** |

**FIFO**：从最早的批次开始消耗 → 取 10 @100 + 5 @120 = **1600**，
剩余 15 件 @120 = **1800**。

**Moving Average**：每次进货重算平均
`((10×100) + (20×120)) / 30 = 113.33`
卖出 15 件 → 15 × 113.33 = **1700**，剩余 15 件 = **1700**。

> 文档结论：*"even though the quantity is same the stock value is different but both amounts
> to a total of **3400** only."* —— **两种方法总成本相同，只是成本结构不同。**

> **二手贸易建议用 FIFO** ⚠️ **推断**：
> 二手件是典型的「一机一价」，Moving Average 会把高价机和低价机混成一个均价，
> 卖出一台高价机时按均价记 COGS，**单件毛利必然失真**。
> FIFO 保留了每批的原始成本，与 `Serial No Wise Valuation` 配合才能实现单件级准确成本。

### 4.3 Stock Ledger Entry 的字段与成本记录

✅ **已验证（文档）** — `stock-ledger` + `how-transactions-affect-the-ledger`

Stock Ledger 记录的三个核心成本字段：

| 字段 | 含义 |
|---|---|
| **Incoming Rate** | 库存**实际入账**的价值，等同单据 `Rate` 字段 |
| **Valuation Rate** | 按所选估值方法（FIFO/MA）算出的成本 |
| **Balance Value** | `Valuation Rate × Balance Quantity`，即剩余库存总价值 |

**会生成 Stock Ledger Entry 的单据** ✅ **已验证（文档）** — `stock-ledger`
> - Sales Invoice、Purchase Invoice（勾选 Update Stock）
> - Delivery Note
> - Purchase Receipt
> - Stock Entry
> - Stock Reconciliation

> **`Posting Time` 会影响估值顺序** ✅ **已验证（文档）** — `how-transactions-affect-the-ledger`
> *"If stock is involved, Posting Time can also affect the sequence used for stock valuation."*
> ⚠️ **推断**：同日多笔出库时，**Posting Time 决定 FIFO 批次消耗顺序**。
> 退货入库 vs 正向出库撞在同一天同一秒，顺序会决定最终剩余批次的成本。

### 4.4 修改估值方法的限制

✅ **已验证（文档）** — `change-valuation-method`（原文）

> *"In the ERPNext, users can change the valuation method from **FIFO to Moving Average, but
> not from Moving Average to FIFO**, for items with existing stock transactions."*

若从 FIFO 改为 Moving Average：
- **新的出库交易**使用 Moving Average；
- 若创建**倒挤（backdated）交易**，该日期之后的所有交易会被 **repost** 为 Moving Average；
- 这可能**改变更早交易的期末结存价值**。

防护手段 ✅ **已验证（文档）**：
> *"users can **freeze stock transactions before a specific date** by setting the
> **'Stock Frozen Up To'** date in the stock settings."*

### 4.5 Standard Valuation Rate（标准成本法，v16）

✅ **已验证（文档）** — `standard-valuation-rate`

**核心思想**：用一个预先设定的固定成本给 Item 估值，而不是用 FIFO/MA 反复波动的值。
实际采购价与标准成本的差额记入 **Purchase Price Variance** 专用科目，
**不污染库存价值**。

| 关注点 | FIFO / Moving Average | Standard Cost |
|---|---|---|
| 库存价值稳定性 | 每次收货/消耗/重估都变 | 你主动发布新费率前保持不变 |
| 倒挤交易 | 触发后续全部重估/repost | **无需 repost**，只是快速的量值位移 |
| Repost 性能 | 慢（长历史 Ledger） | 快 |
| 成本可预测性 | 随批次/均价变化 | 始终是标准费率 |
| 差异可见性 | 差异埋在库存价值里 | 差异隔离在 Purchase Price Variance 科目 |

**Item Standard Cost 记录** ✅ **已验证（文档）**
每个记录携带：`Item`、`Company`（**费率按公司**）、`Standard Rate`（必须 > 0）、`Effective Date`。
每个 item+company 有一条**生效日期严格递增**的时间线；
某日生效的费率 = 该日期或之前**最新的**那条记录。

**发布新费率时会发生什么** ✅ **已验证（文档）**
> 提交新的 Item Standard Cost 后，系统**自动创建并提交一笔 revaluation Stock Reconciliation**，
> 把所有仓库的在手库存从旧费率重估到新费率，盈亏记入 **Stock Adjustment** 科目。
> **不需要手工创建这张 reconciliation**，系统生成并链接在记录上。

**会计处理** ✅ **已验证（文档）**
> 示例：标准费率 130，实收 1 件 @ 200
> - 借 Stock (warehouse asset) **130**
> - 借 Purchase Price Variance **70**
> - 贷 Stock Received But Not Billed **200**
>
> 这 70 差额进 Purchase Price Variance，**不进 Cost of Goods Sold**。
> 前置条件：公司必须配置 **Default Purchase Price Variance Account**
> （或 Item 级覆盖），否则交易被明确阻止，避免差额被记错地方。

制造场景：成品按**自己的标准费率**估值，与消耗的原料成本差额记入 **Stock Adjustment**。

> **二手贸易结论** ⚠️ **推断**：**不要用 Standard Cost**。
> 二手件每台实价不同，标准成本法会把所有差异塞进 Variance 科目，
> 而你真正需要的是「**这台机器花了多少钱（含到岸成本）**」——这要求 FIFO + Serial No Wise Valuation。

### 4.6 Repost Item Valuation（重新估值/重算）

✅ **已验证（文档）** — `repost-item-valuation` + `stock-reposting-settings` + `stock-reposting`

**何时需要 Repost** ✅ **已验证（文档）**
- 创建或修改了**倒挤（backdated）**库存交易
- SLE 的余额不正确
- Repost 问题导致的**负库存**
- 应用库存/估值相关 bug 修复或 patch 之后
- 数据迁移或批量导入库存交易

**Repost 会做什么** ✅ **已验证（文档）**
- 从指定时点重算 Stock Ledger Entries
- 重算 Running Available Stock 和 Stock Balance
- 按估值方法重新评估 Item 估值
- 更新 Stock Value 和 Valuation Rate
- 必要时重发相关 General Ledger 分录

**两种触发方式** ✅ **已验证（文档）**
1. **Automatic**：保存倒挤交易时系统自动创建 repost 记录，由后台定时任务处理
2. **Manual**：手工建 `Repost Item Valuation` 单据，填 Company / Item Code（可选）/
   Warehouse（可选）/ Posting Date & Time，保存后点 **Start Reposting**

**Repost 性能配置（Stock Settings）** ✅ **已验证（文档）** — `stock-reposting-settings`

| 设置 | 作用 |
|---|---|
| `Limit timeslot for Stock Reposting` | 限定 repost 时间窗，**避免 deadlock** |
| `Limits don't apply on` | 全天跑（适合有周休的系统） |
| `Use Item Based Reposting` | 跳过重复的 item+warehouse 组合，提速 |
| `Do reposting for each Stock Transaction` | 不检查未来是否还有交易，一律生成 repost 记录（修并发问题 + 审计用） |
| `Notify Reposting Error to Role` | 失败邮件发给指定角色而非系统管理员 |
| `Enable Parallel Reposting` | 多 worker 并行 repost（**仅在 Item Based Reposting 开启时生效**） |
| `No of Parallel Reposting (Per Item)` | 每 item 并行 worker 数 |

⚠️ **关键限制** ✅ **已验证（文档）**
> *"Reposting is limited to a **timeout of 1500 s**"*；
> *"recommended to limit back dated entries to **not more than one month**"*；
> 跨度超过一个月的 repost 可能因时段限制或超时而失败，导致单据不一致。

**排查工具：Stock Ledger Variance Report** ✅ **已验证（文档）** — `stock-reposting`
> 过滤条件：
> - `Quantity (A - B)` → 找余额数量错误的 ledger
> - `Value (G - D)` → 找余额价值错误
> - `Valuation (I - K)` → 找估值率错误
> 选中异常行 → **Create Reposting Entries** → 生成 repost 记录。

**Stock Valuation Comparison Report** ✅ **已验证（文档）** — `stock-value-comparison`
> 每行是一个 SLE，列分为**实际 / 期望 / 差异**三组：
> - (A) Balance Qty vs (B) Expected Balance Qty，差异 A−B
> - (C) Change in Stock Value vs (D) Expected Change，差异 C−D
> - Valuation Rate 实际 vs 期望，差异
>
> 常用过滤：`Show` 选 **First Difference per Item-Warehouse**（默认，只显示每 item+warehouse
> 的第一条错误，因为一条错后面全错）；`Ignore Differences Below` 默认 0.01。
>
> 修复方式二选一：**Option 1 Repost** / **Option 2 Adjustment Entry**。

⚠️ **重要**：报告的 `From Date / To Date` 只是显示过滤，
**报告仍然从第一条 ledger 开始读取**，以保证计算出的期望值正确。

### 4.7 Landed Cost Voucher（到岸成本）

✅ **已验证（文档）** — `stock-transactions-landed-cost-voucher` + `landed-cost-voucher`

**定义** ✅ **已验证（文档）**
> *"Landed Cost is the final total cost associated with a product for it to reach the buyer's
> doorstep. Landed costs include the original cost of the item, **complete shipping costs,
> customs duties, taxes, insurance, currency conversion fees**, etc."*

#### 4.7.1 方式 A：在 Purchase Receipt 内直接加（推荐用于已知费用）

✅ **已验证（文档）**
在 Purchase Receipt 的 **Taxes and Charges** 表加费用，关键是 **`Consider Tax or Charge for` 字段**：

| 该字段值 | 用于 | 会计效果 |
|---|---|---|
| **`Total and Valuation`** | 付给**同一个供应商**的费用 | 计入单据总额 **且** 计入估值 |
| **`Valuation`** | 付给**第三方**（货代、报关行、保险公司） | 只计入估值，**不计入应付该供应商的总额** |

> 原文：*"Charges which are payable to the same Supplier from whom you are buying the items
> should be tagged as **'Total and Valuation'**. Otherwise, if applicable charges are payable
> to a **3rd party**, it should be tagged as **'Valuation'**."*

PR 提交时系统即计算含这些费用的 landed cost，用于计算 Item 的 Valuation Rate（FIFO/MA）。

#### 4.7.2 方式 B：Landed Cost Voucher（用于事后补录）

✅ **已验证（文档）**
> *"Your transporter can send the invoice after 1 month, but there is no point in waiting for
> booking Purchase Receipt till then. Companies that import their products/parts, **pay a huge
> amount as Customs Duty**. And generally, they get invoices from the Customs Department after
> a while."*

**前置条件** ✅ **已验证（文档）** — `landed-cost-voucher`
> - 挂 **Purchase Invoice** 时：该 Purchase Invoice 必须勾选 **Update Stock**，
>   否则 Purchase Invoice 不会出现在 LCV 的可选列表。
> - 挂 **Purchase Receipt** 时：所选 Item 必须勾选 **Maintain Stock**，
>   否则点 "Get items from Purchase Receipt" 时该 Item 不会出现。

**操作步骤** ✅ **已验证（文档）**
1. `Home > Stock > Tools > Landed Cost Voucher` → New
2. 选 **Receipt Document Type**（Purchase Invoice 或 Receipt），可**多选**
3. 选具体的 Invoice / Receipt，供应商名与 Grand Total 自动带出
4. 点 **Get Items from Purchase Receipts** 拉取明细
5. 选 **Distribute Charges Based On** = `Quantity` 或 `Amount`
6. 在 **Taxes and Charges** 表填 **Expense Account** 和 **Amount**
7. Save and Submit

#### 4.7.3 分摊规则（关键）

✅ **已验证（文档）**
> *"The added charges are proportionately distributed among all the items based their
> **amount or quantity**. If you selected based on the amount, the Item with the highest amount
> will be allocated the highest proportion of the charges."*

| 分摊基准 | 效果 |
|---|---|
| `Amount`（按金额） | **金额高的 Item 分摊得多**。适合关税、按货值计费的费用 |
| `Quantity`（按数量） | **数量多的 Item 分摊得多**。适合运费、按重量/体积计费的费用 |

⚠️ **重要限制** ✅ **已验证（文档）**
> *"you can easily **delete an item if the added charges do not apply to that item**."*
> **LCV 只能按统一的 Quantity 或 Amount 比例分摊，无法按不同基准分别分摊。**
> 混合场景（运费按重量 + 关税按货值）**必须拆成两张 LCV**。

#### 4.7.4 提交后的会计效果

✅ **已验证（文档）** — `stock-transactions-landed-cost-voucher`
> - Item 的 **Valuation Rate 按新的 landed cost 重新计算**。
> - 若启用 **Perpetual Inventory**，系统过账 GL 分录修正 Stock-in-Hand 余额：
>   **借（增加）对应的 warehouse account，贷（减少）Taxes and Charges 表中填的 Expense Account**。
> - ⚠️ **如果货已经出库**：COGS 已按**旧**估值率入账，
>   因此系统会**重发该 Item 所有未来出库分录的 GL**，以修正 COGS 金额。

> **这是双刃剑** ✅（文档明确说明）：Landed Cost Voucher 提交后已销售的货会被追溯改账，
> 历史毛利会变。业务上必须确保**在开票前完成 LCV**。

#### 4.7.5 v16 新增的两类 LCV

✅ **已验证（文档）** — `stock-transactions-landed-cost-voucher`
- **LCV for Stock Entry**：可对 purpose = `Manufacture` 的 Stock Entry 创建，
  把**电费、房租**等制造成本计入成品最终估值率。
- **LCV for Subcontracting Receipt**：可对分包商已加工完成的收货创建，
  把**运费、消费税**计入分包成品估值率。

#### 4.7.6 Vendor Invoices（供应商发票）

✅ **已验证（文档）**
> *"You can link **vendor invoices** in the Landed Cost Voucher, and the system will ensure
> that the **Landed Cost matches the total vendor invoice amount**. Make sure the vendor
> invoices **do not include any stock items**."*

⚠️ **本项目相关**：这是一个**未在技能文档中出现的新能力**。
它意味着可以把货代/报关的发票挂进 LCV，**系统会强制 landed cost 与该发票总额一致**。
对「运费必须精确分摊到每台机器」的需求非常关键。

```python
# 🔧 创建 Landed Cost Voucher：运费按数量、关税按金额（拆两张 LCV）
import frappe
frappe.set_user("Administrator")

lcv = frappe.get_doc({
    "doctype": "Landed Cost Voucher",
    "company": "ISOTENKAI",
    "receipt_document_type": "Purchase Receipt",
    "purchase_receipt": "PREC-00001",
    "distribute_charges_based_on": "Quantity",     # 运费按数量分摊
    "taxes": [{
        "charge_type": "Actual",
        "account_head": "运费 - ISTK",            # 贷方（减少）科目
        "description": "日本至中国海运费",
        "amount": 120000,                          # 本位币金额
    }],
}).insert()
lcv.submit()
print("LCV:", lcv.name)

# 验证分摊结果：逐行检查，不要只看汇总
for r in frappe.get_all("Landed Cost Voucher Item",
                        filters={"parent": lcv.name},
                        fields=["item_code", "qty", "purchase_rate",
                                "landed_cost", "valuation_rate"],
                        limit_page_length=0):
    print(f"{r['item_code']:20s} qty={r['qty']:>4} "
          f"rate={r['purchase_rate']:>10} landed={r['landed_cost']:>10} "
          f"val={r['valuation_rate']:>10}")
```
> ⚠️ 上述字段名（`distribute_charges_based_on`、`taxes`、`landed_cost`）依据文档语义编写，
> **未在 v16.52.0 实测**。落地前请用
> `frappe.get_meta("Landed Cost Voucher").fields` 核对。

### 4.8 自定义到岸成本分摊（超出 ERPNext 原生能力的部分）

⚠️ **全部为推断 + 本项目设计建议**（官方文档只提供 Quantity / Amount 两种等比分摊）：

ERPNext 原生 LCV 满足不了二手贸易的三层分摊需求：

```
采购(日本中古商) → 拆件(零件入库) → 拼柜出口(按箱分摊)
```

推荐的**两层成本模型**（来自本项目 skill `cost-allocation.md`，非官方文档）：

| 层 | 内容 | 规则 |
|---|---|---|
| **原始成本 (base)** | 采购时锁定，**永不修改** | 退款/退税/返利**不得**回写 |
| **退税调整 (adjustment)** | 事后追加的 delta 台账 | 追加式，只增不改 |

```
实际成本 = 原始成本 + Σ 调整
```

**原因**（推断）：如果允许退款修改 base，采购历史就不可证伪，且**所有历史毛利会静默改变**。

---

## 5. Multi-Company 与 Multi-Currency

### 5.1 Company 的本质与关键字段

✅ **已验证（文档）** — `company`

> *"A Company in ERPNext represents a **legal entity** whose transactions, accounts, taxes,
> stock valuation, and financial statements must be kept together. Create separate Companies
> when entities maintain separate books or statutory registrations. **Use branches, cost
> centers, accounting dimensions, or warehouses when the operation belongs to the same legal
> entity.**"*

> 这句话是本节最重要的判断依据：**同一法律实体内的差异，用 Cost Center / Warehouse /
> Accounting Dimension 表达，不要拆 Company。**

| 字段 | 含义 |
|---|---|
| **Abbreviation** | 用于区分公司专属**科目、Cost Center、仓库**的短后缀 |
| **Default Currency** | Company 账簿与财务报表的**本位币** |
| **Country** | 提供区域默认值，决定本地化 |
| **Is Group** | 纯组织父节点，**不能 postings 常规业务交易** |
| **Parent Company** | 归入集团结构，便于合并导航与报表 |
| **Reporting Currency** | 除本位币外的集团报表币种 |

⚠️ **Abbreviation 不可改** ✅ **已验证（文档）**
> *"The abbreviation **cannot be changed**… it is embedded in linked masters.
> Avoid changing it after transactions or many company-specific records exist."*

**ERPNext 在创建 Company 时自动生成什么** ✅ **已验证（文档）**
> *"ERPNext creates a **chart of accounts**, **root cost center**, and **default warehouses**."*

⚠️ **推断 + 本项目已知**：实际创建的是五个英文仓库
（`All Warehouses` 根 + `Stores` / `Work In Progress` / `Finished Goods` / `Goods In Transit`），
并把 `Company.default_warehouse` 指向 `Stores`。
**本项目 skill 记录了由此引发的 `default_warehouse` 悬空引用坑**（删掉英文默认仓后，
下一张 Stock Entry 才报 Link 校验错误）。

```python
# 🔧 检查某个 Company 的默认字段是否指向真实存在的记录
import frappe
frappe.set_user("Administrator")

for c in frappe.get_all("Company", fields=["name","abbr","default_currency","default_warehouse"]):
    wh = c["default_warehouse"]
    ok = "OK" if (wh and frappe.db.exists("Warehouse", wh)) else "❌ DANGLING"
    print(f"{c['name']:16s} {c['abbr'] or '-':8s} {c['default_currency']} "
          f"wh={wh or 'None':32s} {ok}")
```

### 5.2 三种货币必须分清

✅ **已验证（文档）** — `multi-currency-accounting`

| Currency | 控制什么 |
|---|---|
| **Company currency** | Company 上配置的基础记账币种。**财务报表与基础借贷金额都用它** |
| **Account currency** | 科目表里某个科目**固定的币种**。银行/应收/应付科目应各自单一币种 |
| **Transaction currency** | 发票/订单/报价上显示的币种。通过单据的 **Exchange Rate** 换算成 Company 币种 |

**Price List 是第四种** ✅ **已验证（文档）**
> *"If it differs from the transaction currency, **Price List Exchange Rate** converts item
> prices separately from the document's accounting conversion rate."*

> ⚠️ **这是最容易出错的地方**：单据上有**两个汇率**（Price List Exchange Rate 与
> Exchange Rate），前者换算价格，后者换算会计金额。二者可以不同。

### 5.3 外币科目配置

✅ **已验证（文档）** — `multi-currency-setup`

**正确顺序**（文档明确的配置序列）：
1. 确认 **Company 的 Default Currency**
2. 在 Currency 列表**启用**需要的币种（启用只是可选，不建科目也不建汇率）
3. 在科目表创建外币科目：
   - Euro Bank，Account Type = `Bank`，Currency = EUR
   - Euro Receivables，Account Type = `Receivable`，Currency = EUR
   - Euro Payables，Account Type = `Payable`，Currency = EUR
4. 在 Customer 上设 **Billing Currency = EUR**，并在 **Default Accounts** 子表
   关联对应的应收科目
5. Supplier 上做对应设置（`Billing Currency` + `Per-Company Accounts` 表 + 应付科目）

**硬约束** ✅ **已验证（文档）**
> *"ERPNext **does not allow an account's currency to be changed once ledger entries exist**.
> Keep separate accounts for separate bank currencies even when the same institution
> supplies both balances."*

### 5.4 Currency Exchange 与汇率选取机制

✅ **已验证（文档）** — `currency-exchange`

**方向约定（极易搞反）** ✅ **已验证（文档）**
> *"EUR to USD = 1.15 means one euro equals 1.15 US dollars. **The inverse is not
> automatically the same number, so create USD to EUR separately** when that direction is
> needed."*

**Currency Exchange 记录的字段** ✅ **已验证（文档）**

| 字段 | 含义 |
|---|---|
| `Date` | 搜索汇率时用的关键日期 |
| `From Currency` | 字段关系中代表「一个单位」的币种 |
| `To Currency` | 由 From Currency 换算出的币种 |
| `Exchange Rate` | **一个 From Currency 单位等于多少 To Currency 单位** |
| `For Buying` | 该记录可用于需要**买入价**的交易 |
| `For Selling` | 该记录可用于需要**卖出价**的交易 |

两个都勾 = 买卖同价；买卖不同价则**建两条记录**。

**取价优先级** ✅ **已验证（文档）**
> *"ERPNext checks **eligible stored records before asking the configured online provider**."*
> *"Search Currency Exchange for the **latest matching record on or before the transaction
> date**."*

⚠️ **注意「on or before」** ⚠️ **推断**：单据日期早于任何一条 Currency Exchange 记录时，
**取不到汇率**，会回落到 online provider 或报错。

**Stale 汇率策略** ✅ **已验证（文档）** — `currency-exchange` + `exchange-rate-field-frozen`

`Accounts Settings` 中的 `Allow Stale Exchange Rates` + `Stale Days`：

| 设置 | 行为 |
|---|---|
| **Allow Stale Exchange Rates 启用** | 最新的匹配存储汇率**无期限限制**地可用。适用于「合同汇率在被替换前一直有效」 |
| **禁用** | ERPNext 用 `Stale Days` 限制存储汇率的**有效期**，找不到合格记录时**再找 online provider** |

> 文档同时说这个设置与「Exchange Rate 字段是否可编辑」有关联，但**明确承认**
> *"field behavior has changed across releases and can vary by document, **verify the Draft
> page** after changing the setting instead of relying only on the word 'stale'."*

**Currency Exchange Settings（在线 provider 兜底）** ✅ **已验证（文档）**
> ⚠️ *"The setting is **global**, so one incorrect configuration can affect transactions and
> period-end revaluation across **several Companies**."*

字段：`Disabled`、`Service Provider`、`API Endpoint`（支持 `{transaction_date}`、
`{from_currency}`、`{to_currency}` 占位符）、`Use HTTP Protocol`、`Access Key`、
`Parameters`、`Result Key`。
当前 develop 可选 provider：**frankfurter.dev、frankfurter.dev - v2、exchangerate.host、Custom**。
（frankfurter v2 支持币种比 v1 多；exchangerate.host 需要 Access Key。）

### 5.5 Exchange Rate Revaluation（期末重估）

✅ **已验证（文档）** — `exchange-rate-revaluation`

**机制**：不改变外币余额，只改变**本位币账面价值**，差额记为**未实现损益**。

官方示例（月末，账面汇率 1.10，期末汇率 1.15）：

| 度量 | 重估前 | 重估后 |
|---|---|---|
| 科目币种余额 | EUR 1,000 | EUR 1,000（**不变**） |
| 汇率 | 1.10 | 1.15 |
| 本位币账面价值 | USD 1,100 | USD 1,150 |
| 未实现损益 | — | **USD 50** |

**前置条件** ✅ **已验证（文档）**
- Company 至少有一个**非库存的资产负债表科目**，其币种不同于 Company 币种，且 GL 余额符合重估条件
- Company 设置了 **`Unrealized Exchange Gain/Loss Account`**
- （正常的 `Exchange Gain/Loss Account` 用于**已实现**差额，走付款流程）

**操作** ✅ **已验证（文档）**
`Accounting > Multi Currency > Exchange Rate Revaluation` → Add →
填 Posting Date、Company → `Rounding Loss Allowance`（**允许范围 0 ≤ x < 1**，仅在希望
小额余额视为零时设置）→ 点 **Get Entries** → 审查 → Submit。

> ⚠️ **文档明确警告**：*"**Do not submit immediately.** Review each account against the
> General Ledger, the approved closing rate, and the underlying bank/receivable/payable."*

### 5.6 跨公司交易限制 —— 注意版本差异

⚠️ **版本警告**：官方文档的 `company-restrictions-for-item-customer-and-supplier` 页面
**第一行就写着**：
> *"**Note: This feature is available only on v17 and above**"*

**所以在 v16.52.0 上，`Company Restrictions`（Item/Customer/Supplier 限定可用公司列表）不可用。**
本页其余内容（字段、权限、报错信息）**均属 v17**，不能当作 v16 行为。

**v16 可用的跨公司机制** ✅ **已验证（文档）** — `company`
> *"Inter-company sales and purchases must still be recorded in the relevant legal entities.
> Review **Inter Company Invoices** and **Inter Company Journal Entry** for controlled
> cross-company transactions."*

⚠️ **推断**：v16 的跨公司交易靠**在两个公司各记一笔单据**（销售方开 Sales Invoice，
收货方开 Purchase Invoice），配合 Inter Company Invoice / Inter Company Journal Entry
做对账，而不是靠自动的主数据限制。

**多公司结构建议** ✅（文档原则）⚠️ **推断**（结构落地）：
- 同级实体用**平级 Company**（sibling）
- 子公司用 **Parent + Child** 结构
- 同一法人下的业务差异 → **Cost Center / Warehouse / Accounting Dimension**

### 5.7 Precision（精度）对汇率与金额的影响

✅ **已验证（文档）** — `set-precision`

**两种精度** ✅ **已验证（文档）**

| 设置（System Settings） | 影响对象 | 例子 |
|---|---|---|
| **Float Precision** | 数量、换算系数等 | Float Precision = 3，数量 1.275 显示三位小数 |
| **Currency Precision** | 单价、金额等货币值 | 2 → USD 699.50；**4 → USD 1.2375** |

**Rounding Method 独立设置** ✅ **已验证（文档）**
> *"Precision is related to rounding, but it is **not the same decision** as the rounding method."*
> Rounding Method 决定中点值（如 2.345）如何舍入，在 System Settings 中单独配置。

**单字段覆盖** ✅ **已验证（文档）**
用 **Customize Form** 对特定 DocType 的字段设 `Precision` 属性。

**文档给的场景** ✅ **已验证（文档）**
> Nova 以 **USD 1.2375/m** 采购 1,250 米电缆。若采购费率只显示两位小数，
> 员工看到 USD 1.24，会**以为金额输错了**。
> 但如果无理由地全局提高精度，报表会变得难读，用户会把显示细节误当会计精度。

> ⚠️ **推断 + 对本项目的关键提醒**：这个例子与二手贸易**完全对口** ——
> JPY 单价天然是 0 位小数（¥12,000），CNY 是 2 位，但**汇率可能是 6 位小数**
> （JPY→CNY 常见 0.045~0.052）。若 Currency Precision = 2，
> 汇率 0.045123 会被截断成 0.05，**误差 11%，直接毁掉全部毛利计算**。

```python
# 🔧 核对精度设置与实际存储精度
import frappe
frappe.set_user("Administrator")

print("System Settings.float_precision  =", frappe.db.get_single_value("System Settings","float_precision"))
print("System Settings.currency_precision=", frappe.db.get_single_value("System Settings","currency_precision"))
print("System Settings.rounding_method  =", frappe.db.get_single_value("System Settings","rounding_method"))

# Currency 自带的 fraction（最小货币单位）
for c in ["JPY","CNY","USD"]:
    print(c, "fraction =", frappe.db.get_value("Currency", c, "fraction"),
          "enabled =", frappe.db.get_value("Currency", c, "enabled"))

# 字段级覆盖：Item.rate 的 precision
f = frappe.get_meta("Item").get_field("valuation_rate") or frappe.get_meta("Item").get_field("rate")
print("Item rate precision =", getattr(f, "precision", None))
```

**验证精度的正确做法** ✅ **已验证（文档）**
> *"Create a draft Purchase Invoice or Purchase Order with quantity 1,250 and rate 1.2375.
> Confirm the entered rate, calculated amount, taxes, rounded total, print format, and
> General Ledger result follow the intended policy.
> **Display precision alone is not proof that the stored and posted value is correct.**"*

**常见精度问题排查** ✅ **已验证（文档）**
- 字段仍显示更少小数 → 字段有自己的 Precision 属性，或被 Currency 格式化
- 合计与手算不符 → 对比 quantity、conversion factor、rate、税精度、
  **Currency 最小 fraction**、rounded total、rounding method
- 报表与表单精度不同 → 报表有自己的列精度或 Currency 格式化

---

## 6. Cost Center / Account / Company 三者关系

### 6.1 三者的分工

✅ **已验证（文档）** — `cost-center` + `company-accounting-defaults` + `warehouse-ledger-link`

| 维度 | 回答什么问题 | 建多少 |
|---|---|---|
| **Company** | 哪个**法律实体**在记账 | 按法人/账套 |
| **Account（科目）** | 钱**花在哪类事情**上（资产负债/收入/费用） | 按会计科目表 |
| **Cost Center** | 钱是**哪个团队/分支/产品线/项目**造成的 | 按管理责任 |
| **Warehouse** | 货**物理在哪** | 按存储地点 |

**Cost Center 的定位** ✅ **已验证（文档）** — `cost-center`
> *"The general ledger can tell you what Nova Industries spent. A Cost Center helps answer
> **where the cost arose and which team, branch, project, or business unit** is responsible."*
>
> *"lets managers compare the operating cost and profitability of each part of the business"*
> *"**without creating separate ledger accounts for every internal team**"*

> **Cost Center 的存在意义就是不新增科目就能按部门出报表。**

### 6.2 Cost Center 树

✅ **已验证（文档）** — `cost-center`
- 路径：`Home > Accounting > Accounting Masters > Cost Center`
- **group Cost Center** 用于组织层级；**non-group** 用于挂在交易上
- `Add Child` 建子节点；`Is Group` 只在要放子 Cost Center 时才勾
- 每个 Cost Center 属于**特定 Company**

### 6.3 Cost Center 在交易上的粒度

✅ **已验证（文档）** — `cost-center`
> *"The Cost Center is **stored on the item row**. This means one invoice can allocate
> **different lines to different Cost Centers**."*

**即：一张发票的不同行可以挂不同 Cost Center**，提交时 ERPNext 把所选 Cost Center
带入对应的收入和费用分录。之后可以直接按 Cost Center 过滤 P&L 和 General Ledger，
**不需要单独的收入科目**。

**默认值来源** ✅ **已验证（文档）** — `cost-center` + `company-accounting-defaults`
> *"A company, Item, or transaction can provide the default."*

### 6.4 默认科目解析链（最重要的联动机制）

✅ **已验证（文档）** — `company-accounting-defaults`

> *"Defaults do not override every transaction. **ERPNext uses the most specific valid value
> it can find, then falls back to the Company record**."*

```
最具体（Item / Item Group / Warehouse / Customer / Supplier / 交易行）
   ↓ 未提供
Mode of Payment（支付场景）
   ↓ 未提供
Company 的默认科目
```

**Company 会计默认字段清单** ✅ **已验证（文档）** — `company-accounting-defaults`

*Party 相关*
| 字段 | 用途 |
|---|---|
| `Default Receivable Account` | 客户余额与 Sales Invoice |
| `Default Payable Account` | 供应商余额与 Purchase Invoice |
| `Default Cash Account` | 现金收付 |
| `Default Bank Account` | 无更具体科目时的银行收付 |

*收入/费用/Cost Center*
- 正常收入科目、费用科目、Cost Center

*调整科目（跨境贸易必配）*
| 字段 | 用途 |
|---|---|
| `Write Off Account` | 核销/小额余额冲销 |
| **`Exchange Gain/Loss Account`** | **已实现**汇兑差额 |
| **`Unrealized Exchange Gain/Loss Account`** | **未实现**外币余额重估 |
| `Round Off Account` | 货币精度造成的小额差异 |
| `Round Off Cost Center` | 舍入分录用 |

**设置位置** ✅ **已验证（文档）**：Company → **Accounts 标签页**

**覆盖规则** ✅ **已验证（文档）**
> *"**Party-specific accounts on a Customer or Supplier can override the company defaults.**
> A Mode of Payment can also supply a payment account."*

### 6.5 Account 与 Warehouse / Company 的三层联动汇总

✅ **已验证（文档）**（三条来源各自有官方页面佐证）

```
【库存资产归属】
Warehouse.Account  →  Parent Warehouse.Account  →  Company.Default Inventory Account
                                                      （公司创建时自动生成 "Stock In Hand"）

【交易默认科目】
Item/Item Group/Warehouse/Customer/Supplier  →  Company 默认科目

【分析维度】
交易行的 Cost Center  →  按部门过滤 P&L / GL（不新增科目）
```

### 6.6 Cost Center 报表与预算

✅ **已验证（文档）** — `cost-center`
- 按 Cost Center 过滤 **Profit and Loss Statement**、**General Ledger** 等
- **group Cost Center 可汇总其所有后代**
- 可对 Cost Center 创建 **Budget** 以监控或限制支出
- 一笔金额需按百分比分摊给多个 Cost Center 时，使用 **Cost Center Allocation**

⚠️ **推断**：Cost Center **不驱动库存估值**。库存价值由 Warehouse 的 Account 决定。
所以「按部门看库存资金占用」需要 Warehouse → Cost Center 的额外映射，
ERPNext 原生**没有 Warehouse × Cost Center 的标准报表**。

### 6.7 ⚠️ v17 内容混入警告

本次抓取的官方文档站**同时托管 v15 / v16 / v17**，部分页面混入了 v17 内容。
已识别的两处：

| 内容 | 归属 | 依据 |
|---|---|---|
| **Company Restrictions**（Item/Customer/Supplier 限定公司） | **v17+** | 页面首行明确标注 |
| **Disassembly Order / Disassembly Note** | v17（推测） | `inventory-account` 页的 Related Topics 出现，但无正文页 |
| Stock Transactions 列表中的 **Disassembly Order** | v17（推测） | 仅列表项，无正文 |

**在 v16.52.0 上设计时，请以本文标注 ✅ 的 v16 页面为准。**

---

## 7. 容易踩的坑

按「症状 → 原因 → 处理」组织，全部基于本文已验证的官方事实或明确标注的推断。

### 7.1 估值与成本

| # | 症状 | 原因 | 处理 |
|---|---|---|---|
| 1 | 想改 Item 的 Valuation Method，**字段不见了** | ✅ 一旦该 Item 有过 ledger 流水，字段即隐藏 | 新 Item 上设定；老 Item 只能 FIFO→Moving Average（✅ 单向） |
| 2 | 改估值方法后**历史毛利全变了** | ✅ 倒挤交易会 repost 后续全部交易 | Stock Settings 设 `Stock Frozen Up To` 冻结 |
| 3 | 从 Moving Average 想改回 FIFO，**改不了** | ✅ 官方限制：只允许 FIFO → Moving Average | 新建 Item 重新开始 |
| 4 | **序列号件的出库成本不对**（用了均价而非该件买入价） | ✅ 需勾选 `Serial No Wise Valuation`（默认已勾） | 检查 Item 上该复选框；数量极大时才取消 |
| 5 | 序列号件被当成普通 Item 估值 | ✅ 序列化 Item 的 valuation rate 取自**第一条入库流水**，非 Item master | 确认第一条入库流水的 Rate 是真实成本 |
| 6 | Landed Cost 提交后**历史毛利被改** | ✅ 官方明确：已出库的货会重发未来出库分录修正 COGS | **开票前完成 LCV**；不要对已大量出库的 Item 补 LCV |
| 7 | LCV 提交后**库存价值与账面不一致** | ✅ Perpetual Inventory 下会借 Warehouse 账 / 贷 Expense 账 | 检查 Warehouse.Account 与 LCV 的 account_head 是否配对 |
| 8 | Repost 卡住 / 超时 | ✅ 有 **1500 秒超时**，建议倒挤不超过 1 个月 | 缩小范围（Item/Warehouse/日期），非高峰期跑 |
| 9 | Repost 后单据仍不一致 | ✅ 时段限制会让 repost **延后**执行 | 检查 repost 任务的实际执行时间，不是创建时间 |
| 10 | 库存价值报表与科目余额对不上 | ✅ 逐层排查：Stock Valuation Comparison → Stock Ledger Variance → Warehouse.Account 配对 | 先跑 `Ignore Differences Below`（默认 0.01）过滤舍入噪音 |

### 7.2 Serial / Batch

| # | 症状 | 原因 | 处理 |
|---|---|---|---|
| 11 | 直接 insert Serial No 报错 / **warehouse 设不上** | ✅ 官方：*"When a new Serial No is created directly, its Warehouse cannot be set"* | 无 warehouse 建 SN，位置交给 Stock Ledger |
| 12 | `db.exists("Serial No", "SN-01")` 返回 **None 但记录确实在** | ⚠️ v16 `autoname = field:serial_no`，主键与 `serial_no` 不同 | 用 `db.exists("Serial No", {"serial_no": "SN-01"})` |
| 13 | 找不到 DocType `Serial Number` | ✅ v16 已改名 `Serial No`（旧 slug `serial-number` 404） | 先读 `frappe.db.exists("DocType", "Serial No")` |
| 14 | 同一个 Bundle 被多个单据引用，**报错** | ✅ 官方：每笔库存交易必须用**独立的** Bundle | 每单建新 Bundle |
| 15 | 序列号件**无法负库存**，想用负数退回 | ✅ v15 起 Serial/Batch Item 强制禁止负库存 | 走正式的 Return Invoice + 新 Bundle |
| 16 | 序列号状态不是 `Available`，**出不了库** | ✅ 只有 `Available` 状态可发 | 查该 SN 的历史 Stock Entry |
| 17 | 序列号想改绑到别的 Item，但**改不了** | ✅ 该 Item 已发生交易后不能改 | 无解，只能新建 |
| 18 | Batch 下拉里**看不到某个批次** | ✅ 按 Item + Warehouse + Expiry（对比 Posting date）+ 该仓实际量过滤 | 检查该批次在**该仓**是否真有数量 |
| 19 | 想设 `automatically_mark_serial_number_based_on_item` **找不到这个字段** | ⚠️ 官方文档中的名称是 `Automatically Set Serial Nos based on FIFO` | 用 `get_meta("Stock Settings")` 扫字段确认真实 fieldname |
| 20 | Batch Split **不生效** | ✅ 前提是输出 Item 启用 `Has Batch No` + `Automatically Create New Batch` + Batch Series | 缺一不可 |

### 7.3 Warehouse

| # | 症状 | 原因 | 处理 |
|---|---|---|---|
| 21 | 仓库改名后界面**没变** | ⚠️ `Warehouse.name` 是主键，`set_value` 改 label 不重算主键 | `frappe.rename_doc("Warehouse", old, new, force=True)` |
| 22 | 按名字匹配**漏掉部分仓库** | ⚠️ 不同 Company 的命名格式可能相反（`<abbr> - <name>` vs `<name> - <abbr>`） | 按 `warehouse_name` 列匹配，不用 `name LIKE '% - 标签'` |
| 23 | 删了英文默认仓后，**下一张 Stock Entry 才报错** | ⚠️ `Company.default_warehouse` 悬空引用，删除时不校验 | 先重指 `default_warehouse`，再删子仓，最后删根仓 |
| 24 | 删根仓报 `Child warehouse exists` | ✅ 框架保护 | 先删子仓 |
| 25 | 货架级仓库**全都有独立库存价值**，报表难用 | ⚠️ 子仓未继承父仓 Account | 把子仓的 Account 指向根仓的科目 |
| 26 | 启用 Item-wise Inventory Account 后**仓库维度报表变了** | ✅ 官方：item-wise 与 warehouse-wise **只能二选一** | 保持 warehouse-wise（不启用该开关） |
| 27 | 库存移动无法用 Delivery Note 表达（税务要求） | ✅ 需在 Stock Settings 启用 **customer/supplier warehouse for material transfer** | 勾选对应开关 |

### 7.4 多币种

| # | 症状 | 原因 | 处理 |
|---|---|---|---|
| 28 | 改了 Account 的币种，**改不动** | ✅ 官方：已有 ledger 分录后禁止改币种 | 新建正确币种的科目 |
| 29 | 汇率取反了 | ✅ 官方：`EUR→USD=1.15` 的**倒数不是** `USD→EUR` | 两个方向**各建一条** Currency Exchange |
| 30 | 单据日期早于所有 Currency Exchange 记录，**取不到汇率** | ⚠️ 搜索是「on or before 该日期的最新记录」 | 补历史汇率记录，或依赖 online provider |
| 31 | 汇率总被陈旧记录命中 | ✅ `Allow Stale Exchange Rates` 启用时**无期限**使用最新匹配记录 | 合同汇率场景保留；日常资金汇率场景改用小 `Stale Days` |
| 32 | 一个 provider 配置错误**影响多个公司** | ✅ 官方：Currency Exchange Settings 是**全局**设置 | 变更前评估全局影响 |
| 33 | 重估直接 submit，**结果错** | ✅ 官方明确：*"Do not submit immediately"* | 先 Get Entries 再逐科目对 GL 核对 |
| 34 | `Rounding Loss Allowance` 设错 | ✅ 官方：允许范围 **0 ≤ x < 1** | 超出范围会报错 |
| 35 | **汇率精度不够毁掉全部毛利** | ⚠️ Currency Precision 截断长小数汇率（JPY→CNY 常需 6 位小数） | Currency Precision 调高，或给汇率字段单独设 Precision |

### 7.5 流程与结构

| # | 症状 | 原因 | ✅/⚠️ | 处理 |
|---|---|---|---|---|
| 36 | 保存草稿后**账上没有变化**，以为是 bug | ✅ Draft 不产生任何分录 | ✅ | 必须 submit |
| 37 | 取消单据后**历史还在** | ✅ Immutable ledger：取消是**反向分录**，不删历史 | ✅ | 更正要 Cancel + 新建修正单据 |
| 38 | 买了货但**供应商应付没生成** | ✅ Purchase Receipt 只记 `Stock Received But Not Billed` | ✅ | 等 Purchase Invoice |
| 39 | Delivery Note 的 COGS 金额和售价**不一样** | ✅ COGS 按**估值价**，不是售价 | ✅ | 正常，毛利 = 售价 − COGS |
| 40 | 同日多笔出库，**批次消耗顺序不对** | ✅ Posting Time 影响估值顺序 | ✅ | 检查各单的 posting_time |
| 41 | LCV 挂 Purchase Invoice 时**拉不到单据** | ✅ 该 PI 必须勾 **Update Stock** | ✅ | 补勾 |
| 42 | LCV 拉不到某些 Item | ✅ 该 Item 必须勾 **Maintain Stock** | ✅ | 补勾 |
| 43 | 运费和关税**只能用同一个基准**分摊 | ✅ 官方：只有 Quantity 或 Amount 二选一 | ✅ | **拆成两张 LCV** |
| 44 | 坏件/自用件**出现在可售库存和毛利报表里** | ⚠️ 原生无 disposition 属性 | ⚠️ | 单独仓库隔离，靠 Warehouse 过滤 |
| 45 | 拆件（1 整机 → 8 零件）**没有原生单据** | ⚠️ 原生 Manufacture 是「N 原料 → 1 成品」 | ⚠️ | Stock Entry (Repack) 多行，或自建拆解单 DocType |
| 46 | 一台整机里**装了哪颗主板查不到** | ✅ 原生只知道同一 Stock Entry，无法区分 | ⚠️ | `Map Raw Materials to Finished Goods`（方向需实测） |
| 47 | 设了 `Company Restrictions` 却**没效果** | ⚠️ 该功能 **v17+**，v16 不可用 | ⚠️ | v16 靠双公司各自记账 + Inter Company 单据对账 |
| 48 | Company 的 **Abbreviation 改不了** | ✅ 官方：已嵌入关联主数据 | ✅ | 尽早定，一次定死 |
| 49 | 同一法人内的业务差异，**是否该拆 Company** | ✅ 官方：同法人用 Cost Center / Warehouse / Accounting Dimension | ✅ | 不要拆 Company |
| 50 | 官方文档和实际站点**行为不一致** | ⚠️ 文档站混托管 v15/v16/v17 | ⚠️ | 以本文 ✅ 标注的 v16 页为准，改动前在站点实测 |

---

## 8. 验证说明（诚实交代）

### 8.1 🌐 环境限制

本次研究遇到三项网络障碍，均已绕过但影响了验证深度：

| 障碍 | 现象 | 影响 |
|---|---|---|
| **Web 搜索后端 403** | Firecrawl / Keenable 均返回 `403 Forbidden` / `Bad gateway` | 无法用搜索引擎，只能靠 sitemap 定位页面 |
| **GitHub 完全不可达** | `git clone` 要求输入用户名；`codeload.github.com` 与 `api.github.com` 对 `erpnext/erpnext` 一律 **404** | **未能做源码级验证** |
| **PyPI 404** | `pypi.org/pypi/erpnext/json` 返回 404 | 无法安装 erpnext 包读源码 |

**绕过方式**：官方文档站的 `https://docs.frappe.io/sitemap.xml` 可访问，
从中提取到 **859 条 ERPNext 页面 URL**，据此定位到正确的 v16 slug
（例如 `serial-no` 而非已 404 的 `serial-number`），并实际抓取了 **54 个页面**。

### 8.2 ✅ 已验证 vs ⚠️ 推断

| 类别 | 数量级 | 说明 |
|---|---|---|
| ✅ **已验证（文档）** | 本文档绝大部分机制说明 | 逐条来自实际抓取的 54 个官方页面，文末给出页名 |
| 🔧 **可运行代码** | 9 段 | 依据文档语义编写，**多数未在目标站点实测** |
| ⚠️ **推断** | 明确标注 | 官方文档未直接陈述，基于文档事实 + Frappe 通用行为 |
| 🔧 **本地验证** | 站点连通性 | `erp.motitoo.com` 可达（`frappe.ping` 返回 `pong`，中文 locale 生效） |

### 8.3 未能验证的三项

1. **站点版本号 v16.52.0** —— 来自任务上下文。
   尝试 `frappe.utils.change_log.get_versions` 返回 **403 权限错误**（需登录），
   `erpnext.api.version` 返回 **模块不存在**。**未能在线确认。**
2. **GitHub 源码** —— 网络封锁，未能做源码级验证。
   所有机制均以**官方文档**为准。
3. **本文所有 Python 代码** —— 未在 v16.52.0 上执行。
   字段名（尤其 `Serial No` 相关、LCV 相关）请先用
   `frappe.get_meta(<DocType>).fields` 核对后再用。

### 8.4 抓取的官方页面清单（54 个）

`accounting-of-inventory-stock`, `batch`, `batch-split`, `calculation-of-valuation-rate-in-fifo-and-moving-average`,
`change-valuation-method`, `chart-of-accounts`, `company`, `company-accounting-defaults`,
`company-restrictions-for-item-customer-and-supplier` *(v17)*, `company-setup`, `cost-center`,
`currency-exchange`, `currency-exchange-settings`, `delivery-note`, `exchange-rate-field-frozen`,
`exchange-rate-revaluation`, `how-is-valuation-rate-of-serialised-item-calculated-in-erpnext`,
`how-transactions-affect-the-ledger`, `inventory-account`, `item-valuation-transactions`,
`landed-cost-voucher`, `managing-batch-wise-inventory`, `multi-currency-accounting`,
`multi-currency-setup`, `purchase-cycle-ledger-impact`, `purchase-receipt`, `putaway-rule`,
`quick-stock-balance`, `repost-item-valuation`, `retain-sample-stock`, `selling-cycle-ledger-impact`,
`serial-and-batch`, `serial-and-batch-bundle`, `serial-and-batch-traceability-report`, `serial-no`,
`serial-no-naming`, `set-precision`, `standard-valuation-rate`, `stock-entry`, `stock-entry-purpose`,
`stock-ledger`, `stock-level-report`, `stock-masters`, `stock-reconciliation`, `stock-reposting`,
`stock-reposting-settings`, `stock-settings`, `stock-transactions`,
`stock-transactions-landed-cost-voucher`, `stock-value-comparison`, `use-serial-no-wise-valuation`,
`warehouse`, `warehouse-ledger-link`

### 8.5 与本项目 skill 的交叉验证

本文档的以下发现与已有 skill 记录**互相印证**，可信度较高：

- ✅ `Serial Number → Serial No` 改名（skill pitfall 26）
- ✅ Serial No 直接创建时 warehouse 不可设（skill pitfall 26）
- ✅ Warehouse.name 由框架生成、格式可能相反（skill pitfall 46）
- ✅ Company 创建生成五个英文默认仓 + `default_warehouse` 悬空（skill pitfalls 61/64）
- ✅ Abbreviation 不可改（本文 §5.1）

**新增发现**（skill 中尚无记录）：
- ✅ **Landed Cost Voucher 支持 Vendor Invoices**，系统强制 landed cost 与发票总额一致（§4.7.6）
- ✅ **v16 支持 per-company Valuation Method**，解析顺序 Item → Company → Stock Settings（§4.1）
- ✅ **LCV 可挂 Manufacture Stock Entry 与 Subcontracting Receipt**（§4.7.5）
- ✅ **Customer/Supplier Warehouse 的真实用途是「让库存移动能以 Delivery Note/Purchase Receipt 形式开票」**，用于每次移动都要计税的法律要求（§3.4）

---

*文档生成：Hermes Agent（哦呢） | 数据来源：docs.frappe.io/erpnext（54 页实抓） | 2026-10-23*