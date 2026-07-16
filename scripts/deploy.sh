#!/usr/bin/env bash
# NAS 部署脚本：拉代码 → 构建 → 启动 → 数据库迁移
# 用法:
#   sudo ./scripts/deploy.sh          # 日常更新（默认）
#   sudo ./scripts/deploy.sh --init   # 首次部署（创建 .env）
#   sudo ./scripts/deploy.sh --restart  # 仅重启，不拉代码、不构建

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

COMPOSE_FILE="docker-compose.prod.yml"

log() { echo "[deploy] $*"; }
die() { echo "[deploy] ERROR: $*" >&2; exit 1; }

run_compose() {
  sudo docker compose -f "$COMPOSE_FILE" "$@"
}

compose_profiles() {
  if [[ -f .env ]] && grep -qE '^CLOUDFLARE_TUNNEL_TOKEN=.+' .env; then
    echo "--profile" "tunnel"
  fi
}

init_env() {
  if [[ -f .env ]]; then
    log ".env 已存在，跳过初始化"
    return
  fi
  if [[ ! -f .env.example ]]; then
    die ".env.example 不存在"
  fi
  sudo cp .env.example .env
  log "已从 .env.example 创建 .env"
  log "请先编辑 .env（POSTGRES_PASSWORD、密钥、CORS_ORIGINS 等），然后重新运行: sudo ./scripts/deploy.sh"
  exit 0
}

pull_code() {
  if [[ -d .git ]]; then
    log "拉取最新代码..."
    # 不要用 sudo 拉代码：root 没有当前用户的 SSH/凭据，会卡在认证
    if [[ -n "${SUDO_USER:-}" ]]; then
      sudo -u "$SUDO_USER" git -C "$ROOT_DIR" pull --ff-only
    else
      git pull --ff-only
    fi
  else
    log "非 git 目录，跳过 git pull"
  fi
}

build_and_up() {
  local profiles
  profiles="$(compose_profiles)"
  log "构建并启动服务..."
  # shellcheck disable=SC2086
  run_compose $profiles up -d --build
}

restart_services() {
  local profiles
  profiles="$(compose_profiles)"
  log "重启服务（不构建）..."
  # shellcheck disable=SC2086
  run_compose $profiles up -d
}

run_migrations() {
  log "等待 API 容器就绪..."
  sleep 3
  log "执行数据库迁移..."
  run_compose exec -T api alembic upgrade head
}

health_check() {
  log "健康检查..."
  if run_compose exec -T api python -c "
import urllib.request
r = urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=10)
print(r.read().decode())
" 2>/dev/null; then
    log "服务启动成功"
  else
    log "健康检查未通过，请查看日志: sudo docker compose -f $COMPOSE_FILE logs api"
  fi
}

show_status() {
  log "当前容器状态:"
  run_compose ps
}

# ---- main ----
MODE="${1:-update}"

case "$MODE" in
  --init|init)
    init_env
    pull_code
    build_and_up
    run_migrations
    health_check
    show_status
    ;;
  --restart|restart)
    [[ -f .env ]] || die ".env 不存在，请先运行: sudo ./scripts/deploy.sh --init"
    restart_services
    show_status
    ;;
  --help|-h)
    echo "用法:"
    echo "  sudo ./scripts/deploy.sh           日常更新（pull + build + migrate）"
    echo "  sudo ./scripts/deploy.sh --init    首次部署（创建 .env + 启动）"
    echo "  sudo ./scripts/deploy.sh --restart 仅重启容器（不 pull、不 build）"
    ;;
  update|"")
    [[ -f .env ]] || init_env
    pull_code
    build_and_up
    run_migrations
    health_check
    show_status
    ;;
  *)
    die "未知参数: $MODE（使用 --help 查看用法）"
    ;;
esac
