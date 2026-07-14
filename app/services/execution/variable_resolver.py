import re
from typing import Any, Callable, Optional


class VariableResolver:
    """解析模板字符串中的 ${...} 变量引用。"""

    VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")

    def resolve(self, template: Any, variables: dict[str, Any]) -> Any:
        if isinstance(template, str):
            return self._resolve_string(template, variables)
        if isinstance(template, dict):
            return {k: self.resolve(v, variables) for k, v in template.items()}
        if isinstance(template, list):
            return [self.resolve(item, variables) for item in template]
        return template

    def _resolve_string(self, template: str, variables: dict[str, Any]) -> Any:
        if (
            template.startswith("${")
            and template.endswith("}")
            and template.count("${") == 1
        ):
            var_path = template[2:-1]
            value = variables.get(var_path)
            if value is not None:
                return value
            if var_path.startswith("env."):
                return template
            return template

        def replacer(match: re.Match[str]) -> str:
            var_path = match.group(1)
            value = variables.get(var_path)
            if value is not None:
                return str(value)
            return match.group(0)

        return self.VAR_PATTERN.sub(replacer, template)

    def resolve_env_variables(
        self,
        template: Any,
        env_resolver_func: Callable[[str], Optional[str]],
    ) -> Any:
        if isinstance(template, str):
            return self._resolve_env_string(template, env_resolver_func)
        if isinstance(template, dict):
            return {
                k: self.resolve_env_variables(v, env_resolver_func)
                for k, v in template.items()
            }
        if isinstance(template, list):
            return [
                self.resolve_env_variables(item, env_resolver_func) for item in template
            ]
        return template

    def _resolve_env_string(
        self,
        template: str,
        env_resolver_func: Callable[[str], Optional[str]],
    ) -> str:
        def replacer(match: re.Match[str]) -> str:
            var_path = match.group(1)
            if var_path.startswith("env."):
                env_key = var_path[4:]
                value = env_resolver_func(env_key)
                return value if value is not None else match.group(0)
            return match.group(0)

        return self.VAR_PATTERN.sub(replacer, template)

    def extract_refs(self, obj: Any) -> list[str]:
        refs: list[str] = []
        if isinstance(obj, str):
            refs.extend(self.VAR_PATTERN.findall(obj))
        elif isinstance(obj, dict):
            for value in obj.values():
                refs.extend(self.extract_refs(value))
        elif isinstance(obj, list):
            for item in obj:
                refs.extend(self.extract_refs(item))
        return refs
