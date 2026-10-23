#!/usr/bin/env bash
#
# 创建独立站点（新项目）
#
# 用途：为 J2C_ISTK / C2J_ISTK / 后续项目各建一个独立 site，
#       物理隔离（独立数据库），互不干扰。
#
# 用法（在服务器上跑）：
#   /opt/erp/deploy/new_site.sh <site名> <app名>
#
# 例：
#   /opt/erp/deploy/new_site.sh c2j.motitoo.com c2j_istk
#
# 做的事：
#   1. 前置检查（站点不存在、app 已部署）
#   2. bench new-site（建库 + 装 app）
#   3. bench migrate（跑 app 的 patch → 建仓库/品类/设置）
#   4. 打印后续步骤（域名配置）
#
# 不做（刻意留给后续单独处理）：
#   - Nginx 域名代理（等真实域名确定后配）
#   - Let's Encrypt 证书
#   - 备份脚本（备份是按库名全覆盖的，新库自动包含）

set -euo pipefail

SITE="${1:-}"
APP="${2:-}"

if [ -z "$SITE" ] || [ -z "$APP" ]; then
    echo "用法: $0 <site名> <app名>"
    echo "例:   $0 c2j.motitoo.com c2j_istk"
    exit 1
fi

echo "════════════════════════════════════════"
echo " 创建独立站点"
echo "   site : $SITE"
echo "   app  : $APP"
echo "════════════════════════════════════════"
echo ""

BENCH_CONTAINER="frappe_docker-backend-1"
BENCH_DIR="/home/frappe/frappe-bench"

bench() {
    docker exec "$BENCH_CONTAINER" bash -c "cd $BENCH_DIR && bench $1"
}

py() {
    docker exec "$BENCH_CONTAINER" bash -c \
        "cd $BENCH_DIR/sites && /home/frappe/frappe-bench/env/bin/python -c \"$1\""
}

# ── 1. 前置检查 ──
echo "【1/4】前置检查"

if docker exec "$BENCH_CONTAINER" test -d "$BENCH_DIR/sites/$SITE"; then
    echo "  ✗ 站点 $SITE 已存在，退出"
    exit 1
fi
echo "  ✓ 站点不存在"

if ! docker exec "$BENCH_CONTAINER" test -d "$BENCH_DIR/apps/$APP"; then
    echo "  ✗ app $APP 未部署（$BENCH_DIR/apps/$APP 不存在）"
    echo "     先把 app 代码放到 /opt/erp/apps/$APP"
    exit 1
fi
echo "  ✓ app $APP 已部署"

# 数据库 root 密码：从现有站点复用（同一台 MariaDB）
DB_PASS=$(docker exec "$BENCH_CONTAINER" bash -c \
    "cd $BENCH_DIR/sites/erp.motitoo.com && python3 -c 'import json; print(json.load(open(\"site_config.json\"))[\"db_password\"])' 2>/dev/null" || true)

if [ -z "$DB_PASS" ]; then
    echo "  ✗ 读不到数据库密码（现有站点 site_config.json）"
    exit 1
fi
echo "  ✓ 数据库凭据就绪"

# ── 2. 建站 ──
echo ""
echo "【2/4】bench new-site（建库 + 装 app）"

bench "new-site $SITE \
    --db-type mariadb \
    --db-host db \
    --db-port 3306 \
    --mariadb-root-username root \
    --mariadb-root-password '$DB_PASS' \
    --admin-password '$DB_PASS' \
    --install-app $APP" 2>&1 | tail -25

if ! docker exec "$BENCH_CONTAINER" test -d "$BENCH_DIR/sites/$SITE"; then
    echo "  ✗ 站点创建失败"
    exit 1
fi
echo ""
echo "  ✓ 站点已创建"

# ── 3. migrate（跑 app patch 建主数据）──
echo ""
echo "【3/4】bench migrate（初始化主数据）"

bench "--site $SITE migrate" 2>&1 | tail -15

echo ""
echo "  ✓ 主数据初始化完成"

# ── 4. 验证 + 后续步骤 ──
echo ""
echo "【4/4】验证"

docker exec "$BENCH_CONTAINER" bash -c \
    "cd $BENCH_DIR/sites && /home/frappe/frappe-bench/env/bin/python - <<'PYEOF'
import frappe
frappe.init(site='$SITE')
frappe.connect()
print('  已安装 app:', [a for a in frappe.get_installed_apps()])
print('  Module   :', frappe.get_all('Module Def', filters={'app_name':'$APP'}, pluck='name'))
print('  Company  :', frappe.get_all('Company', pluck='name'))
print('  仓库     :', len(frappe.get_all('Warehouse', pluck='name')))
print('  品类     :', len(frappe.get_all('Item Group', pluck='name')))
print('  UOM      :', len(frappe.get_all('UOM', pluck='name')))
print('  Brand    :', len(frappe.get_all('Brand', pluck='name')))
print('  Item     :', len(frappe.get_all('Item', pluck='name')))
PYEOF" 2>&1 | grep -v Warning

echo ""
echo "════════════════════════════════════════"
echo " 完成：$SITE"
echo "════════════════════════════════════════"
echo ""
echo "后续步骤（域名确定后做）："
echo "  1. Nginx 加 server 块，proxy_pass 到 backend 的 $SITE"
echo "  2. 申请 Let's Encrypt 证书"
echo "  3. bench set-sites-frappe $SITE"
echo ""
echo "注意："
echo "  - 本机访问用 http://<服务器IP>:8000/$SITE"
echo "  - 数据库是独立库，备份脚本按库名全覆盖，新库自动包含"
