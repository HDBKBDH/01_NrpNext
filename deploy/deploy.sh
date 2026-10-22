#!/usr/bin/env bash
# secondtrade app 部署脚本 — 莱卡云
#
# 用法：
#   ./deploy.sh              # 部署 + migrate + 备份
#   ./deploy.sh --no-backup  # 跳过备份
#
# 前置：本地已把 app/secondtrade 同步到服务器 /opt/erp/staging/secondtrade

set -euo pipefail

SERVER="${SERVER:-root@110.42.60.173}"
SITE="${SITE:-erp.motitoo.com}"
BACKEND="frappe_docker-backend-1"
APPS="/home/frappe/frappe-bench/apps"
SITES="/home/frappe/frappe-bench/sites"
STAGING="${STAGING:-/opt/erp/staging/secondtrade}"

DO_BACKUP=1
[ "${1:-}" = "--no-backup" ] && DO_BACKUP=0

echo "==> 目标: $SERVER / site=$SITE"

if [ "$DO_BACKUP" -eq 1 ]; then
    echo "==> [1/5] 部署前备份"
    ssh "$SERVER" "/usr/local/bin/frappe-backup.sh" 2>&1 | grep -E '[✓✗]' || true
else
    echo "==> [1/5] 跳过备份"
fi

echo "==> [2/5] 传入 app 到容器"
ssh "$SERVER" "docker exec --user root $BACKEND rm -rf $APPS/secondtrade"
ssh "$SERVER" "tar -C $STAGING -cf - ." \
  | ssh "$SERVER" "docker exec -i --user root $BACKEND tar -C $APPS/secondtrade -xf -" 2>/dev/null || {
      # 回退：目标目录不存在时先创建
      ssh "$SERVER" "docker exec --user root $BACKEND mkdir -p $APPS/secondtrade"
      ssh "$SERVER" "tar -C $STAGING -cf - ." \
        | ssh "$SERVER" "docker exec -i --user root $BACKEND tar -C $APPS/secondtrade -xf -"
  }
ssh "$SERVER" "docker exec --user root $BACKEND chown -R frappe:root $APPS/secondtrade"
ssh "$SERVER" "docker exec --user root $BACKEND find $APPS/secondtrade -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true"

echo "==> [3/5] pip install + 注册"
ssh "$SERVER" "docker exec --user root $BACKEND bash -lc 'cd $APPS/secondtrade && /home/frappe/frappe-bench/env/bin/pip install -e . -q'"
ssh "$SERVER" "docker exec --user root $BACKEND bash -lc 'grep -q secondtrade $SITES/apps.txt || echo secondtrade >> $SITES/apps.txt'"
ssh "$SERVER" "docker exec --user root $BACKEND chown frappe:root $SITES/apps.txt"

echo "==> [4/5] bench migrate"
ssh "$SERVER" "docker exec $BACKEND bash -lc 'cd /home/frappe/frappe-bench && bench --site $SITE migrate 2>&1'" \
  | grep -viE 'updating doctypes|syncing|flushing|removing|updating dashboard|queued rebuilding'

if [ "$DO_BACKUP" -eq 1 ]; then
    echo "==> [5/5] 部署后备份"
    ssh "$SERVER" "/usr/local/bin/frappe-backup.sh" 2>&1 | grep -E '[✓✗]' || true
else
    echo "==> [5/5] 跳过备份"
fi

echo ""
echo "✓ 部署完成: https://erp.motitoo.com/"
