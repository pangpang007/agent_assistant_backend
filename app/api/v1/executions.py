from fastapi import APIRouter

router = APIRouter()

# Phase 1 实现:
# GET    /          - 执行记录列表
# GET    /{id}      - 执行详情
# GET    /{id}/nodes - 节点执行详情
# GET    /{id}/logs  - 执行日志
