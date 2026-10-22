#!/bin/bash
# 莱卡云 docker compose 统一入口
#
# 为什么需要这个脚本：
#   docker compose 必须带全部 -f 参数，漏掉任何一个都会退回默认配置，
#   导致 sites / db-data / apps / assets 挂载到别处，出现「数据分叉」和
#   「容器重建后自定义 app 消失」。历史上已因此出过两次事故，所以收敛到一处。
#
# 用法：frappe-compose <原生命令> [参数]
#   frappe-compose up -d
#   frappe-compose ps
#   frappe-compose logs -f backend

cd /opt/erp/frappe_docker
exec docker compose \
  -f compose.yaml \
  -f overrides/compose.mariadb.yaml \
  -f overrides/compose.redis.yaml \
  -f overrides/compose.proxy.yaml \
  -f overrides/compose.bind-mount-db-data.yaml \
  -f overrides/compose.bind-mount-sites.yaml \
  -f overrides/compose.shared-assets.yaml \
  -f overrides/compose.persist-apps.yaml \
  "$@"