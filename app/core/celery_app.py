"""Celery 应用配置。"""

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "tangyuan",
    broker=settings.redis_url,        # 复用 Redis 作为消息代理
    backend=settings.redis_url,        # 结果后端
    include=["app.tasks.knowledge_tasks"],
)

celery_app.conf.update(
    # 序列化
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # 时区
    timezone="UTC",
    enable_utc=True,

    # Worker 配置
    worker_concurrency=4,             # 并发 Worker 数
    worker_max_tasks_per_child=50,    # 每个 Worker 处理 50 个任务后重启（防止内存泄漏）
    worker_prefetch_multiplier=1,     # 每次只预取 1 个任务（文档处理耗时长）

    # 任务路由
    task_routes={
        "process_document": {"queue": "knowledge"},
    },

    # 任务超时
    task_soft_time_limit=300,   # 软超时 5 分钟（抛出 SoftTimeLimitExceeded）
    task_time_limit=600,        # 硬超时 10 分钟（强制终止）

    # 结果过期
    result_expires=3600,        # 结果保留 1 小时
)
