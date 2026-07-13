import enum


class MemoryStrategy(str, enum.Enum):
    none = "none"
    window = "window"
    summary = "summary"


class OutputFormat(str, enum.Enum):
    json = "json"
    markdown = "markdown"
    text = "text"


class ProviderType(str, enum.Enum):
    openai = "openai"
    anthropic = "anthropic"
    google = "google"
    custom = "custom"


class ToolType(str, enum.Enum):
    preset = "preset"
    custom = "custom"


class AuthType(str, enum.Enum):
    none = "none"
    api_key = "api_key"
    bearer = "bearer"


class DocumentStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class FileType(str, enum.Enum):
    pdf = "pdf"
    txt = "txt"
    md = "md"
    csv = "csv"
    docx = "docx"


class ExecutionStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"
    paused = "paused"
    cancelled = "cancelled"


class NodeStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"
    skipped = "skipped"
    paused = "paused"


class LogLevel(str, enum.Enum):
    info = "info"
    warn = "warn"
    error = "error"


class EnvVarType(str, enum.Enum):
    string = "string"
    secret = "secret"


class NodeType(str, enum.Enum):
    """工作流节点类型"""

    start = "startNode"
    end = "endNode"
    agent = "agentNode"
    knowledge_retrieval = "knowledgeRetrievalNode"
    code = "codeNode"
    http = "httpNode"
    template = "templateNode"
    condition = "conditionNode"
    parallel = "parallelNode"
    loop = "loopNode"
    classify = "classifyNode"
    extract = "extractNode"
    review = "reviewNode"
    test = "testNode"
    delay = "delayNode"
    variable_aggregate = "variableAggregateNode"


class AccountType(str, enum.Enum):
    personal = "personal"
    team = "team"
