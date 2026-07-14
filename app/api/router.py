from fastapi import APIRouter

from app.api.v1 import (
    agents,
    auth,
    crypto,
    env_vars,
    executions,
    health,
    knowledge,
    models,
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
api_router.include_router(templates.router, prefix="/v1/templates", tags=["Templates"])
api_router.include_router(executions.router, prefix="/v1/executions", tags=["Executions"])
api_router.include_router(ws.router, prefix="/ws", tags=["WebSocket"])
api_router.include_router(env_vars.router, prefix="/v1/env-vars", tags=["Env Variables"])
