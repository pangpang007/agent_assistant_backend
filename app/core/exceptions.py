from typing import Any, Optional


class AppException(Exception):
    """应用级基础异常"""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: Optional[list[Any]] = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or []
        super().__init__(message)


class NotFoundException(AppException):
    def __init__(self, resource: str, identifier: str = ""):
        msg = f"{resource}不存在"
        if identifier:
            msg = f"{resource} '{identifier}' 不存在"
        super().__init__(code="NOT_FOUND", message=msg, status_code=404)


class UnauthorizedException(AppException):
    def __init__(self, message: str = "未授权，请先登录"):
        super().__init__(code="UNAUTHORIZED", message=message, status_code=401)


class ForbiddenException(AppException):
    def __init__(self, message: str = "无权限访问此资源"):
        super().__init__(code="FORBIDDEN", message=message, status_code=403)


class WorkflowNotFoundError(AppException):
    def __init__(self):
        super().__init__(
            code="WORKFLOW_NOT_FOUND",
            message="工作流不存在",
            status_code=404,
        )


class VersionNotFoundError(AppException):
    def __init__(self, version_number: int):
        super().__init__(
            code="VERSION_NOT_FOUND",
            message=f"版本 v{version_number} 不存在",
            status_code=404,
        )


class UnsupportedNodeTypeError(AppException):
    def __init__(self, node_type: str):
        super().__init__(
            code="UNSUPPORTED_NODE_TYPE",
            message=f"不支持的节点类型: {node_type}",
            status_code=400,
        )


class NodeExecutionTimeoutError(AppException):
    def __init__(self, timeout: int):
        super().__init__(
            code="NODE_EXECUTION_TIMEOUT",
            message=f"节点执行超时（{timeout}秒）",
            status_code=408,
        )


class InvalidImportFormatError(AppException):
    def __init__(self):
        super().__init__(
            code="INVALID_IMPORT_FORMAT",
            message="导入 JSON 格式不合法",
            status_code=400,
        )


class ExecutionNotFoundError(AppException):
    def __init__(self):
        super().__init__(
            code="EXECUTION_NOT_FOUND",
            message="执行记录不存在",
            status_code=404,
        )


class ExecutionNotCancellableError(AppException):
    def __init__(self, status: str):
        super().__init__(
            code="EXECUTION_NOT_CANCELLABLE",
            message=f"当前状态不可取消: {status}",
            status_code=400,
        )


class ExecutionNotPausedError(AppException):
    def __init__(self):
        super().__init__(
            code="EXECUTION_NOT_PAUSED",
            message="执行未在暂停状态",
            status_code=400,
        )


class WorkflowEmptyError(AppException):
    def __init__(self):
        super().__init__(
            code="WORKFLOW_EMPTY",
            message="工作流无节点或边数据",
            status_code=400,
        )


class InvalidReviewNodeError(AppException):
    def __init__(self):
        super().__init__(
            code="INVALID_REVIEW_NODE",
            message="无效的审核节点",
            status_code=400,
        )


class TemplateNotFoundError(AppException):
    def __init__(self):
        super().__init__(
            code="TEMPLATE_NOT_FOUND",
            message="模板不存在",
            status_code=404,
        )


class PresetTemplateProtectedError(AppException):
    def __init__(self):
        super().__init__(
            code="PRESET_TEMPLATE_PROTECTED",
            message="预置模板不可删除/修改",
            status_code=403,
        )


class NoTagToRemoveError(AppException):
    def __init__(self):
        super().__init__(
            code="NO_TAG_TO_REMOVE",
            message="该版本没有标签可删除",
            status_code=400,
        )


class LogNotFoundError(AppException):
    def __init__(self):
        super().__init__(
            code="LOG_NOT_FOUND",
            message="日志不存在",
            status_code=404,
        )


class EnvVarNotFoundError(AppException):
    def __init__(self):
        super().__init__(
            code="ENV_VAR_NOT_FOUND",
            message="环境变量不存在",
            status_code=404,
        )


class EnvVarKeyExistsError(AppException):
    def __init__(self):
        super().__init__(
            code="ENV_VAR_KEY_EXISTS",
            message="变量名已存在",
            status_code=409,
        )


class EnvVarKeyFormatError(AppException):
    def __init__(self):
        super().__init__(
            code="ENV_VAR_KEY_FORMAT",
            message="变量名格式不合法，只允许大写字母、数字和下划线",
            status_code=422,
        )


class EnvVarTypeImmutableError(AppException):
    def __init__(self):
        super().__init__(
            code="ENV_VAR_TYPE_IMMUTABLE",
            message="不允许修改变量类型",
            status_code=400,
        )

