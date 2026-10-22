# secondtrade

二手跨国贸易管理系统 — 日本中古采购 / 拆解 / 跨境运输 / 闲鱼销售

## 模块

- **Disassembly Note** 拆解单：整机 → 零件，成本按采购时参考价权重分摊
- **Logistics Batch** 物流批次：批次运费录入，自动分摊到零件
- **Customs Declaration** 报关单：分解报关 + 凭证管理
- **Item Transit Record** 商品轨迹：多态物流轨迹（货运/携带/往返）
- **Market Price History** 行情价历史：分类批量更新 + 走势图数据源
- **Trade Settings** 贸易配置：单例，资金成本率等

## 编号规则

    整机采购 → 拆解单：YYMMDD-NN        例：261003-01
    零件 SN：YYMMDD-NN-{TYPE}-NN     例：261003-01-CPU-01

TYPE: CPU / MEM / GPU / MB / NVME / PSU / CHS
