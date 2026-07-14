"""
预置数据初始化脚本。
在数据库初始化完成后执行，插入预置 Agent 和预置工具。
幂等设计：检查 is_preset=True 的记录是否已存在，已存在则跳过。
"""

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.template import Template
from app.models.tool import Tool
from app.seeds.preset_templates import PRESET_TEMPLATES

logger = structlog.get_logger()


# ========== 预置 Agent 配置 ==========
PRESET_AGENTS = [
    {
        "name": "产品经理",
        "description": "负责需求分析、用户故事编写和 PRD 文档输出。擅长将模糊的业务需求转化为清晰的产品规格。",
        "system_prompt": """你是一位资深产品经理。你的职责：
1. 深入理解用户需求，提炼核心问题
2. 编写清晰、结构化的 PRD 文档
3. 定义用户故事和验收标准
4. 提供产品策略建议和优先级排序
5. 输出格式规范，使用 Markdown 排版

始终从用户视角出发，关注可行性和商业价值。""",
        "memory_strategy": "window",
        "output_format": "markdown",
        "temperature": 0.7,
        "max_tokens": 4096,
    },
    {
        "name": "前端工程师",
        "description": "精通 React/Vue/TypeScript 等现代前端技术栈，擅长组件化开发和 UI 交互实现。",
        "system_prompt": """你是一位资深前端工程师，精通 React、Vue、TypeScript、Tailwind CSS 等现代前端技术栈。你的职责：
1. 编写高质量、可维护的前端代码
2. 实现响应式布局和流畅的交互体验
3. 遵循组件化设计原则，代码复用
4. 关注性能优化（懒加载、虚拟列表、缓存等）
5. 输出代码包含注释和类型定义

代码风格：函数式优先，hooks 驱动，TypeScript 严格模式。""",
        "memory_strategy": "window",
        "output_format": "markdown",
        "temperature": 0.3,
        "max_tokens": 8192,
    },
    {
        "name": "后端工程师",
        "description": "精通 Python/FastAPI/Node.js 等后端技术栈，擅长 API 设计和数据库建模。",
        "system_prompt": """你是一位资深后端工程师，精通 Python、FastAPI、Node.js、PostgreSQL 等后端技术栈。你的职责：
1. 设计 RESTful API，遵循最佳实践
2. 编写高效、安全的后端服务代码
3. 设计数据库模型和查询优化
4. 关注安全性（认证、授权、输入校验、SQL 注入防护）
5. 编写单元测试和集成测试

代码风格：分层架构（Router → Service → Repository），依赖注入，异步优先。""",
        "memory_strategy": "window",
        "output_format": "markdown",
        "temperature": 0.3,
        "max_tokens": 8192,
    },
    {
        "name": "测试工程师",
        "description": "擅长测试策略制定、测试用例设计和自动化测试脚本编写。",
        "system_prompt": """你是一位资深测试工程师。你的职责：
1. 根据需求文档制定完整的测试策略
2. 设计覆盖正向、反向、边界条件的测试用例
3. 编写自动化测试脚本（pytest/Jest/Cypress）
4. 关注性能测试和安全测试
5. 输出测试报告，包含缺陷分级和优先级

测试用例格式：编号 | 前置条件 | 步骤 | 预期结果 | 优先级""",
        "memory_strategy": "window",
        "output_format": "markdown",
        "temperature": 0.4,
        "max_tokens": 4096,
    },
    {
        "name": "Code Reviewer",
        "description": "专注于代码质量审查，识别代码中的潜在问题、安全风险和改进空间。",
        "system_prompt": """你是一位严谨的代码审查专家。你的职责：
1. 审查代码质量：命名规范、代码结构、可读性
2. 识别潜在 Bug：空指针、竞态条件、资源泄漏
3. 安全审查：SQL 注入、XSS、敏感信息暴露
4. 性能审查：N+1 查询、不必要的循环、内存泄漏
5. 架构建议：设计模式、SOLID 原则、可维护性

审查输出格式：
- 🔴 严重问题（必须修复）
- 🟡 建议改进（推荐修复）
- 🟢 小建议（可选）
- ✅ 优点（值得肯定的做法）""",
        "memory_strategy": "window",
        "output_format": "markdown",
        "temperature": 0.2,
        "max_tokens": 4096,
    },
    {
        "name": "架构师",
        "description": "负责系统架构设计、技术选型、性能优化方案制定和技术债务评估。",
        "system_prompt": """你是一位资深系统架构师。你的职责：
1. 根据业务需求设计系统架构（微服务/单体/事件驱动等）
2. 进行技术选型，分析各方案的优劣
3. 设计数据流和系统交互图
4. 评估性能瓶颈，提供优化方案
5. 制定技术规范和最佳实践
6. 评估技术债务，制定偿还计划

输出架构图时使用 Mermaid 语法，确保可渲染。
始终关注：可扩展性、高可用、安全性、成本效益。""",
        "memory_strategy": "summary",
        "output_format": "markdown",
        "temperature": 0.5,
        "max_tokens": 8192,
    },
]


# ========== 预置工具配置 ==========
PRESET_TOOLS = [
    {
        "name": "网页搜索",
        "description": "搜索互联网信息，获取实时数据和最新资讯。支持关键词搜索、站点过滤等操作。",
        "tool_type": "preset",
        "openapi_spec": {
            "operationId": "web_search",
            "summary": "搜索互联网",
            "parameters": {
                "query": {"type": "string", "description": "搜索关键词", "required": True},
                "num_results": {"type": "integer", "description": "返回结果数量", "default": 10},
                "language": {"type": "string", "description": "语言偏好", "default": "zh-CN"},
            },
        },
        "api_url": None,
        "auth_type": "none",
        "auth_config": None,
    },
    {
        "name": "网页抓取",
        "description": "抓取指定 URL 的网页内容，返回提取后的纯文本。支持自动去噪和结构化提取。",
        "tool_type": "preset",
        "openapi_spec": {
            "operationId": "web_scrape",
            "summary": "抓取网页内容",
            "parameters": {
                "url": {"type": "string", "description": "目标 URL", "required": True},
                "extract_mode": {"type": "string", "description": "提取模式: full/text/markdown", "default": "markdown"},
            },
        },
        "api_url": None,
        "auth_type": "none",
        "auth_config": None,
    },
    {
        "name": "代码执行器",
        "description": "在安全沙箱环境中执行 Python 或 JavaScript 代码，返回执行结果和输出。",
        "tool_type": "preset",
        "openapi_spec": {
            "operationId": "code_execute",
            "summary": "执行代码",
            "parameters": {
                "language": {"type": "string", "description": "编程语言: python/javascript", "required": True},
                "code": {"type": "string", "description": "要执行的代码", "required": True},
                "timeout": {"type": "integer", "description": "超时时间(秒)", "default": 30},
            },
        },
        "api_url": None,
        "auth_type": "none",
        "auth_config": None,
    },
    {
        "name": "文件读写",
        "description": "在受控沙箱中读写文件，支持创建、读取、追加、列表等操作。",
        "tool_type": "preset",
        "openapi_spec": {
            "operationId": "file_operation",
            "summary": "文件操作",
            "parameters": {
                "operation": {"type": "string", "description": "操作类型: read/write/list/delete", "required": True},
                "path": {"type": "string", "description": "文件路径", "required": True},
                "content": {"type": "string", "description": "文件内容(写入时)", "required": False},
            },
        },
        "api_url": None,
        "auth_type": "none",
        "auth_config": None,
    },
    {
        "name": "HTTP 请求",
        "description": "调用任意 REST API，支持 GET/POST/PUT/DELETE 方法和自定义认证。",
        "tool_type": "preset",
        "openapi_spec": {
            "operationId": "http_request",
            "summary": "发送 HTTP 请求",
            "parameters": {
                "method": {"type": "string", "description": "HTTP 方法: GET/POST/PUT/DELETE", "required": True},
                "url": {"type": "string", "description": "请求 URL", "required": True},
                "headers": {"type": "object", "description": "请求头", "required": False},
                "body": {"type": "object", "description": "请求体", "required": False},
                "timeout": {"type": "integer", "description": "超时时间(秒)", "default": 30},
            },
        },
        "api_url": None,
        "auth_type": "none",
        "auth_config": None,
    },
    {
        "name": "JSON 解析",
        "description": "解析、转换和格式化 JSON 数据。支持 JSONPath 查询、字段映射、格式转换。",
        "tool_type": "preset",
        "openapi_spec": {
            "operationId": "json_parse",
            "summary": "JSON 处理",
            "parameters": {
                "operation": {"type": "string", "description": "操作: parse/query/transform/format", "required": True},
                "data": {"type": "string", "description": "JSON 数据", "required": True},
                "expression": {"type": "string", "description": "JSONPath 表达式(query时)", "required": False},
            },
        },
        "api_url": None,
        "auth_type": "none",
        "auth_config": None,
    },
    {
        "name": "文本处理",
        "description": "正则匹配、文本替换、拆分合并、编码转换等文本处理操作。",
        "tool_type": "preset",
        "openapi_spec": {
            "operationId": "text_process",
            "summary": "文本处理",
            "parameters": {
                "operation": {"type": "string", "description": "操作: regex/replace/split/encode/decode", "required": True},
                "text": {"type": "string", "description": "输入文本", "required": True},
                "pattern": {"type": "string", "description": "正则表达式/替换规则", "required": False},
                "options": {"type": "object", "description": "附加选项", "required": False},
            },
        },
        "api_url": None,
        "auth_type": "none",
        "auth_config": None,
    },
]


async def seed_preset_data(db: AsyncSession) -> None:
    """
    初始化预置数据。幂等设计，重复执行不会重复插入。
    """
    await _seed_preset_agents(db)
    await _seed_preset_tools(db)
    await _seed_preset_templates(db)
    await db.commit()
    logger.info("preset_data_seeded")


async def _seed_preset_agents(db: AsyncSession) -> None:
    """插入预置 Agent（如已存在则跳过）"""
    # 检查是否已有预置 Agent
    result = await db.execute(
        select(Agent).where(Agent.is_preset == True).limit(1)
    )
    if result.scalar_one_or_none() is not None:
        logger.info("preset_agents_already_exist, skip")
        return

    for agent_data in PRESET_AGENTS:
        agent = Agent(
            user_id=None,  # 预置 Agent 不属于任何用户，但 FK nullable 需要调整
            is_preset=True,
            **agent_data,
        )
        db.add(agent)

    logger.info("preset_agents_created", count=len(PRESET_AGENTS))


async def _seed_preset_tools(db: AsyncSession) -> None:
    """插入预置工具（如已存在则跳过）"""
    result = await db.execute(
        select(Tool).where(Tool.is_preset == True).limit(1)
    )
    if result.scalar_one_or_none() is not None:
        logger.info("preset_tools_already_exist, skip")
        return

    for tool_data in PRESET_TOOLS:
        tool = Tool(
            user_id=None,  # 预置工具不属于任何用户
            is_preset=True,
            **tool_data,
        )
        db.add(tool)

    logger.info("preset_tools_created", count=len(PRESET_TOOLS))


async def _seed_preset_templates(db: AsyncSession) -> None:
    """插入预置模板（按固定 UUID 幂等）。"""
    created = 0
    for tpl in PRESET_TEMPLATES:
        tpl_id = uuid.UUID(tpl["id"]) if isinstance(tpl["id"], str) else tpl["id"]
        existing = await db.get(Template, tpl_id)
        if existing is not None:
            continue
        db.add(
            Template(
                id=tpl_id,
                user_id=None,
                workflow_id=None,
                name=tpl["name"],
                description=tpl.get("description"),
                category=tpl["category"],
                thumbnail_url=tpl.get("thumbnail_url"),
                use_count=tpl.get("use_count", 0),
                is_preset=True,
                nodes_data=tpl.get("nodes_data") or [],
                edges_data=tpl.get("edges_data") or [],
            )
        )
        created += 1

    if created == 0:
        logger.info("preset_templates_already_exist, skip")
    else:
        logger.info("preset_templates_created", count=created)
