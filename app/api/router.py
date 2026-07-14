from fastapi import APIRouter

from app.api.v1 import (
    agents,
    auth,
    crypto,
    dashboard,
    env_vars,
    executions,
    external_api,
    health,
    knowledge,
    logs,
    models,
    published_apis,
    search,
    teams,
    templates,
    tools,
    users,
    workflows,
    ws,
)

api_router = APIRouter(prefix="/api")

api_router.include_router(health.router, tags=["Health"])
api_router.include_router(crypto.router, prefix="/crypto", tags=["Crypto"])
api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(teams.router, prefix="/teams", tags=["Teams"])

api_router.include_router(agents.router, prefix="/agents", tags=["Agents"])
api_router.include_router(tools.router, prefix="/tools", tags=["Tools"])
api_router.include_router(knowledge.router, prefix="/knowledge", tags=["Knowledge"])
api_router.include_router(models.router, prefix="/models", tags=["Models"])
api_router.include_router(workflows.router, prefix="/workflows", tags=["Workflows"])
api_router.include_router(templates.router, prefix="/templates", tags=["Templates"])
api_router.include_router(executions.router, prefix="/executions", tags=["Executions"])
api_router.include_router(logs.router, prefix="/logs", tags=["Logs"])
api_router.include_router(ws.router, prefix="/ws", tags=["WebSocket"])
api_router.include_router(env_vars.router, prefix="/env-vars", tags=["Env Variables"])

# Phase 7
api_router.include_router(dashboard.router, tags=["Dashboard"])
api_router.include_router(published_apis.router, tags=["Published APIs"])
api_router.include_router(search.router, tags=["Search"])
api_router.include_router(external_api.router, tags=["External API"])
