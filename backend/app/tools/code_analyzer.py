from __future__ import annotations

import ast
import hashlib
import io
import re
import tokenize
from dataclasses import dataclass
from pathlib import PurePosixPath


@dataclass(frozen=True, slots=True)
class ProjectFileSnapshot:
    path: str
    content: str


@dataclass(frozen=True, slots=True)
class FrozenRetrievalSource:
    file: ProjectFileSnapshot
    content_hash: str


@dataclass(frozen=True, slots=True)
class Detector:
    evidence_type: str
    content_pattern: re.Pattern[str]
    strength: str
    explanation: str
    file_pattern: re.Pattern[str] | None = None


@dataclass(frozen=True, slots=True)
class CodeEvidence:
    skill: str
    evidence_type: str
    file_path: str
    line_start: int
    line_end: int
    snippet: str
    strength: str
    explanation: str
    content_hash: str
    context_complete: bool = False
    context_note: str = "仅定位行，尚未补取上下文"
    provenance: str = "portfolio"
    function_line_start: int | None = None
    function_line_end: int | None = None
    source_line_count: int | None = None


def detector(
    evidence_type: str,
    content_pattern: str,
    strength: str,
    explanation: str,
    file_pattern: str | None = None,
) -> Detector:
    return Detector(
        evidence_type=evidence_type,
        content_pattern=re.compile(content_pattern, re.IGNORECASE | re.MULTILINE),
        strength=strength,
        explanation=explanation,
        file_pattern=re.compile(file_pattern, re.IGNORECASE) if file_pattern else None,
    )


DETECTORS: dict[str, tuple[Detector, ...]] = {
    "MySQL": (
        detector("sql_schema", r"\bCREATE\s+TABLE\b", "high", "存在数据库建表语句"),
        detector("sql_query", r"\b(SELECT|INSERT|UPDATE|DELETE)\b", "medium", "存在SQL数据操作"),
        detector("mysql_config", r"jdbc:mysql|mysql", "medium", "存在MySQL连接或依赖配置"),
    ),
    "Redis": (
        detector(
            "redis_dependency",
            r"redis|spring-boot-starter-data-redis",
            "high",
            "显式引入Redis依赖",
            r"(pom\.xml|package\.json|requirements\.txt)$",
        ),
        detector(
            "redis_usage",
            r"\b(?:redis|cache)\.(?:get|set|setex|expire)\s*\(",
            "medium",
            "存在缓存读写调用",
        ),
    ),
    "Java": (
        detector(
            "java_class",
            r"\b(public|private|protected)?\s*(class|interface|enum)\b",
            "medium",
            "存在Java类或接口",
            r"\.java$",
        ),
        detector(
            "java_build",
            r"maven|gradle|spring",
            "medium",
            "存在Java构建配置",
            r"(pom\.xml|build\.gradle)$",
        ),
    ),
    "Spring Boot": (
        detector(
            "spring_annotation",
            r"@(SpringBootApplication|RestController|Service|Repository)",
            "high",
            "使用Spring核心注解",
        ),
        detector(
            "spring_dependency", r"spring-boot-starter", "high", "引入Spring Boot依赖", r"pom\.xml$"
        ),
    ),
    "React": (
        detector(
            "react_import", r"from\s+['\"]react['\"]|require\(['\"]react", "low", "仅直接引入React"
        ),
        detector(
            "react_hooks",
            r"\b(useState|useEffect|useMemo|useQuery)\s*\(",
            "high",
            "存在React Hooks实践",
            r"\.(tsx|jsx)$",
        ),
    ),
    "Vue": (
        detector(
            "vue_sfc",
            r"<template>|defineComponent|<script\s+setup",
            "high",
            "存在Vue单文件组件",
            r"\.vue$",
        ),
    ),
    "TypeScript": (
        detector(
            "typescript_code",
            r"interface\s+\w+|type\s+\w+\s*=|:\s*(string|number|boolean)\b",
            "high",
            "存在TypeScript类型定义",
            r"\.tsx?$",
        ),
        detector(
            "typescript_config",
            r"\"compilerOptions\"|\"strict\"\s*:",
            "high",
            "存在TypeScript严格配置",
            r"tsconfig\.json$",
        ),
    ),
    "Node.js": (
        detector(
            "node_usage",
            r"process\.env|from\s+['\"]node:|express|fastify|koa",
            "medium",
            "存在Node.js运行时或服务端框架调用",
        ),
    ),
    "Python": (
        detector(
            "python_code",
            r"^\s*(?:async\s+)?def\s+\w+\s*\(",
            "high",
            "存在Python函数实现",
            r"\.py$",
        ),
        detector(
            "python_dependency",
            r"fastapi|flask|django|pandas|numpy",
            "medium",
            "存在Python框架依赖",
            r"(requirements\.txt|pyproject\.toml)$",
        ),
    ),
    "FastAPI": (
        detector(
            "fastapi_route",
            r"@(?:app|router)\.(?:get|post|put|patch|delete)\s*\(",
            "high",
            "存在FastAPI路由实现",
            r"\.py$",
        ),
        detector(
            "fastapi_app",
            r"\bFastAPI\s*\(",
            "medium",
            "创建了FastAPI应用实例",
            r"\.py$",
        ),
        detector(
            "fastapi_dependency",
            r"(?:^|\n)\s*fastapi(?:\[.*?\])?\s*(?:==|>=|~=|$)",
            "low",
            "声明了FastAPI依赖",
            r"requirements\.txt$",
        ),
    ),
    "PostgreSQL": (
        detector(
            "postgres_usage",
            r"\bpsycopg(?:2)?\.(?:connect|Connection)\b|postgresql(?:\+[a-z0-9_]+)?://",
            "medium",
            "存在PostgreSQL驱动或连接的实际使用",
            r"\.(py|java|js|ts|properties|ya?ml)$",
        ),
        detector(
            "postgres_dependency",
            r"(?:^|\n)\s*(?:psycopg(?:2)?(?:\[.*?\])?|asyncpg)\s*(?:==|>=|~=|$)",
            "low",
            "声明了PostgreSQL驱动依赖",
            r"requirements\.txt$",
        ),
    ),
    "pytest": (
        detector(
            "pytest_test",
            r"(?:^|\n)\s*(?:async\s+)?def\s+test_\w+\s*\([^)]*\)\s*:[\s\S]{0,1500}?\bassert\b",
            "high",
            "存在包含断言的pytest测试",
            r"(?:^|/)test_.*\.py$|(?:^|/).*_test\.py$",
        ),
        detector(
            "pytest_fixture",
            r"@pytest\.(?:fixture|mark\.)",
            "medium",
            "使用了pytest夹具或测试标记",
            r"\.py$",
        ),
        detector(
            "pytest_dependency",
            r"(?:^|\n)\s*pytest\s*(?:==|>=|~=|$)",
            "low",
            "声明了pytest依赖",
            r"requirements\.txt$",
        ),
    ),
    "REST API": (
        detector(
            "rest_route",
            r"@(GetMapping|PostMapping|RequestMapping)|@(app|router)\.(get|post|put|delete)|app\.(get|post|put|delete)\(",
            "high",
            "定义HTTP路由",
        ),
        detector(
            "rest_response",
            r"ResponseEntity|res\.json|status\((200|201|404)\)",
            "medium",
            "处理HTTP响应",
        ),
    ),
    "Docker": (
        detector("dockerfile", r"^FROM\s+\S+", "high", "存在Docker镜像构建文件", r"Dockerfile$"),
        detector(
            "docker_compose",
            r"^services\s*:",
            "high",
            "存在容器编排配置",
            r"docker-compose.*\.ya?ml$",
        ),
    ),
    "Git": (
        detector(
            "github_actions",
            r"^jobs\s*:|^\s*steps\s*:|pull_request",
            "high",
            "存在持续集成工作流",
            r"\.github/workflows/.+\.ya?ml$",
        ),
        detector(
            "gitignore",
            r"node_modules|\.env|dist|target",
            "low",
            "配置了版本控制忽略规则",
            r"\.gitignore$",
        ),
    ),
    "Linux": (
        detector(
            "shell_script",
            r"^#!/bin/(ba)?sh|\b(grep|awk|sed|chmod|systemctl)\b",
            "medium",
            "存在Linux Shell脚本",
            r"\.(sh|bash)$",
        ),
    ),
}

STRENGTH_ORDER = {"high": 0, "medium": 1, "low": 2}

# Narrow static indicators, never claims of successful operations or performance.
DETECTORS.update(
    {
        "Shell": (
            detector(
                "shell_command",
                r"^\s*(?:curl|systemctl|pg_dump|pg_restore)\s+",
                "medium",
                "存在运维命令脚本；执行结果和错误处理完整性未核验",
                r"\.sh$",
            ),
        ),
        "CI/CD": (
            detector(
                "pipeline_config",
                r"^\s*(?:-\s*)?(?:run|script):\s*\S+",
                "low",
                "存在流水线执行步骤；未证明部署、回滚或运行成功",
                r"(?:\.github/workflows/.*\.ya?ml|\.gitlab-ci\.yml)$",
            ),
        ),
        "监控告警": (
            detector(
                "metric_exposition",
                r"^\s*(?:def\s+(?:generate_latest|start_http_server|make_asgi_app)\s*\(|class\s+(?:Counter|Gauge|Histogram)\s*\()",
                "low",
                "存在指标定义或暴露实现；不证明告警配置、处置或部署运行",
                r"\.py$",
            ),
            detector(
                "alert_rule",
                r"^\s*-?\s*alert:\s*\S+",
                "medium",
                "存在告警规则声明；告警触发和通知送达未核验",
                r"\.ya?ml$",
            ),
        ),
        "索引优化": (
            detector(
                "index_definition",
                r"^\s*CREATE\s+(?:UNIQUE\s+)?INDEX\s+\w+\s+ON\s+",
                "medium",
                "存在索引定义；缺少执行计划及前后对比时不能认定优化收益",
                r"\.sql$",
            ),
        ),
        "备份恢复": (
            detector(
                "backup_command",
                r"^\s*pg_dump\s+",
                "medium",
                "存在备份命令；未证明备份成功、可恢复性或恢复演练",
                r"\.sh$",
            ),
            detector(
                "restore_command",
                r"^\s*pg_restore\s+",
                "medium",
                "存在恢复工具命令；需核对参数，列目录不等于实际恢复",
                r"\.sh$",
            ),
        ),
        "权限管理": (
            detector(
                "sql_grant",
                r"^\s*GRANT\s+(?:SELECT|INSERT|UPDATE|DELETE|ALL|USAGE)\b",
                "medium",
                "存在数据库授权语句；最小权限是否成立及权限验证未核验",
                r"\.sql$",
            ),
        ),
        "数据库监控": (
            detector(
                "db_monitor_query",
                r"\bFROM\s+(?:pg_stat_activity|pg_stat_database|pg_locks)\b",
                "medium",
                "存在数据库状态查询；持续采集、告警和排查效果未核验",
                r"\.sql$",
            ),
        ),
    }
)

DOCUMENT_RUBRICS = {
    "活动策划": (r"目标|目的", r"受众|目标人群|用户群", r"预算|费用", r"排期|时间安排|执行计划"),
    "用户调研": (r"研究问题|调研目标", r"样本|访谈对象", r"问卷|访谈|观察", r"发现|结论|局限"),
    "内容运营": (r"目标|定位", r"受众|用户群", r"选题|内容规划|发布计划", r"指标|复盘|阅读量|转化"),
}


def canonical_skill(skill: str) -> str | None:
    aliases = {
        "sql": "SQL",
        "数据库设计": "SQL",
        "springboot": "Spring Boot",
        "node": "Node.js",
        "ts": "TypeScript",
        "fast api": "FastAPI",
        "postgres": "PostgreSQL",
        "postgresql数据库": "PostgreSQL",
        "py.test": "pytest",
        "运营策划": "活动策划",
    }
    value = skill.strip().lower()
    return aliases.get(value) or next(
        (name for name in (*DETECTORS, "SQL", *DOCUMENT_RUBRICS) if name.lower() == value), None
    )


def _analysis_text(file: ProjectFileSnapshot) -> str:
    """Ignore comments, TODOs and Python docstrings while preserving source line numbers."""
    text = file.content
    if file.path.endswith(".py"):
        try:
            tree = ast.parse(text)
            lines = text.splitlines(keepends=True)
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Expr)
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)
                ):
                    for index in range(node.lineno - 1, node.end_lineno or node.lineno):
                        lines[index] = "\n" if lines[index].endswith("\n") else ""
            text = "".join(lines)
            tokens = tokenize.generate_tokens(io.StringIO(text).readline)
            clean = text.splitlines(keepends=True)
            for token in tokens:
                if token.type == tokenize.COMMENT:
                    line = token.start[0] - 1
                    clean[line] = clean[line][: token.start[1]] + "\n"
            text = "".join(clean)
        except (SyntaxError, tokenize.TokenError, IndentationError):
            return ""
    else:
        # Preserve quoted strings, e.g. URLs and SQL literal values, when removing comments.
        pattern = (
            r"""("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')"""
            r"|(/\*[\s\S]*?\*/|//[^\n]*|\#[^\n]*|--[^\n]*|<!--[\s\S]*?-->)"
        )
        text = re.sub(pattern, lambda m: m[1] if m[1] else "\n" * m[0].count("\n"), text)
    return "\n".join(
        "" if re.search(r"\bTODO\b|\bFIXME\b|尚未实现|待实现|计划实现", line, re.I) else line
        for line in text.split("\n")
    )


def _document_evidence(file: ProjectFileSnapshot, skill: str) -> list[CodeEvidence]:
    if PurePosixPath(file.path).suffix.lower() not in {".md", ".txt"}:
        return []
    if len(file.content.strip()) < 120:
        return []
    # A rubric needs its own substantive line. Repeated text and a keyword-filled
    # single line must not stand in for several independently described elements.
    lines: dict[int, str] = {}
    seen_text: set[str] = set()
    for number, raw_line in enumerate(file.content.splitlines(), start=1):
        line = raw_line.strip()
        normalized = re.sub(r"\s+", "", line)
        if (
            len(line) >= 12
            and not re.search(r"TODO|待填写|待补充|示例|模板", line, re.I)
            and normalized not in seen_text
        ):
            lines[number] = line
            seen_text.add(normalized)
    candidates = [
        [number for number, line in lines.items() if re.search(pattern, line)]
        for pattern in DOCUMENT_RUBRICS[skill]
    ]
    assigned: dict[int, int] = {}

    def assign_rubric(rubric: int, visited: set[int]) -> bool:
        # Maximum matching avoids losing valid evidence when two rubrics share a
        # candidate line but one of them also has another suitable line.
        for number in candidates[rubric]:
            if number in visited:
                continue
            visited.add(number)
            previous = assigned.get(number)
            if previous is None or assign_rubric(previous, visited):
                assigned[number] = rubric
                return True
        return False

    for rubric in range(len(candidates)):
        assign_rubric(rubric, set())
    if len(assigned) < 3:
        return []
    return [
        CodeEvidence(
            skill=skill,
            evidence_type="document_structure",
            file_path=file.path,
            line_start=number,
            line_end=number,
            snippet=lines[number][:240],
            strength="medium",
            explanation="文档包含具体评价要素，仅证明材料有相关内容；执行效果和作者贡献需人工核查。",
            content_hash=hashlib.sha256(file.content.encode("utf-8")).hexdigest(),
        )
        for number in sorted(assigned)
    ]


def _line_details(content: str, match_start: int) -> tuple[int, str]:
    line_start_index = content.rfind("\n", 0, match_start) + 1
    line_end_index = content.find("\n", match_start)
    if line_end_index < 0:
        line_end_index = len(content)
    line_number = content.count("\n", 0, match_start) + 1
    snippet = content[line_start_index:line_end_index].strip()
    return line_number, snippet[:240]


MAX_PYTHON_FUNCTIONS_PER_FILE = 4
MAX_PYTHON_SOURCE_LINES = 80
MAX_PYTEST_FUNCTIONS_PER_FILE = 6


def _is_pytest_raises_call(node: ast.AST) -> bool:
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "pytest"
            and node.func.attr == "raises")


def _pytest_implementation_lines(content: str) -> list[int]:
    lines = []
    for function in _python_function_nodes(content):
        if not function.name.startswith("test_"):
            continue
        pending = list(function.body)
        has_assertion = False
        while pending:
            node = pending.pop()
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                continue
            if isinstance(node, ast.Assert):
                has_assertion = True
            if isinstance(node, ast.With) and any(
                _is_pytest_raises_call(item.context_expr) for item in node.items
            ):
                has_assertion = True
            # A one-argument call only constructs a context manager. Function-form
            # raises needs a callable argument; static detection does not execute it.
            if (_is_pytest_raises_call(node) and len(node.args) >= 2
                and isinstance(node.args[1], ast.Name | ast.Attribute | ast.Lambda
                               | ast.Subscript | ast.Call)):
                has_assertion = True
            pending.extend(ast.iter_child_nodes(node))
        if has_assertion:
            lines.append(function.lineno)
    # Sample across the file instead of letting early happy-path tests consume
    # all slots. Names/line positions select source only; they never prove coverage.
    if len(lines) > MAX_PYTEST_FUNCTIONS_PER_FILE:
        return [lines[round(i * (len(lines) - 1) / (MAX_PYTEST_FUNCTIONS_PER_FILE - 1))]
                for i in range(MAX_PYTEST_FUNCTIONS_PER_FILE)]
    return lines


def _python_function_nodes(content: str) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Return top-level functions and direct class methods, never nested closures."""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []
    nodes: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            nodes.append(node)
        elif isinstance(node, ast.ClassDef):
            nodes.extend(
                child
                for child in node.body
                if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef)
            )
    return sorted(nodes, key=lambda node: node.lineno)


def _has_python_behavior(statement: ast.AST) -> bool:
    if isinstance(statement, ast.Return):
        return statement.value is not None and not (
            isinstance(statement.value, ast.Constant) and statement.value.value is None
        )
    if isinstance(statement, ast.Expr):
        return isinstance(statement.value, ast.Call | ast.Await | ast.Yield | ast.YieldFrom)
    if isinstance(statement, ast.Assign | ast.AugAssign | ast.Delete):
        return True
    if isinstance(statement, ast.AnnAssign):
        return statement.value is not None
    if isinstance(
        statement,
        ast.If
        | ast.For
        | ast.AsyncFor
        | ast.While
        | ast.With
        | ast.AsyncWith
        | ast.Try
        | ast.TryStar
        | ast.ExceptHandler
        | ast.Match
        | ast.match_case,
    ):
        return any(_has_python_behavior(child) for child in ast.iter_child_nodes(statement))
    return False


def _python_function_score(source: str, name: str, requirement_title: str) -> int:
    """Rank useful implementation anchors without relying on a project-specific name."""
    score = 0
    if not name.startswith("_"):
        score += 2
    mutations = len(
        re.findall(r"\b(?:INSERT|UPDATE|DELETE|BEGIN|COMMIT|ROLLBACK)\b", source, re.I)
    )
    score += min(mutations, 4) * 2
    if re.search(r"\.(?:commit|rollback)\s*\(", source, re.I):
        score += 2
    # Only lexical hints that are actually present in the function body. This is
    # a tie-breaker, not a claim that matching a word proves business relevance.
    words = {
        word
        for word in re.findall(r"[a-z][a-z0-9_]{2,}", requirement_title.lower())
        if word not in {"python", "实现", "完成", "使用", "以及", "要求"}
    }
    if words:
        source_lower = source.lower()
        score += sum(1 for word in words if word in source_lower)
    return score


def _python_implementation_anchors(
    content: str, requirement_title: str = ""
) -> list[tuple[int, int]]:
    """Return bounded (line, score) anchors, ranked by observable behavior."""
    lines = content.splitlines()
    ranked = []
    for node in _python_function_nodes(content):
        if not any(_has_python_behavior(statement) for statement in node.body):
            continue
        end = min(node.end_lineno or node.lineno, len(lines))
        source = "\n".join(
            lines[node.lineno - 1 : min(end, node.lineno - 1 + MAX_PYTHON_SOURCE_LINES)]
        )
        ranked.append((_python_function_score(source, node.name, requirement_title), node.lineno))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [(line, score) for score, line in ranked[:MAX_PYTHON_FUNCTIONS_PER_FILE]]


def _python_implementation_lines(
    content: str, requirement_title: str = ""
) -> list[int]:
    return [line for line, _ in _python_implementation_anchors(content, requirement_title)]


def _python_implementation_line(content: str) -> int | None:
    """Compatibility wrapper for callers that only need the strongest anchor."""
    lines = _python_implementation_lines(content)
    return lines[0] if lines else None


def _redis_parameter_usage_line(source: str) -> int | None:
    """Locate a call through an imported Redis-typed parameter, without execution.

    This is deliberately not general type inference: reassigned names and
    ambiguous scopes are refused. An annotation is material evidence, not proof
    that Redis was reached or that the submitted code was executed.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    modules: set[str] = set()
    classes: set[str] = set()
    imports = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "redis":
                    modules.add(alias.asname or alias.name)
                    imports.append(node)
        elif isinstance(node, ast.ImportFrom) and node.module == "redis" and not node.level:
            for alias in node.names:
                if alias.name in {"Redis", "StrictRedis"}:
                    classes.add(alias.asname or alias.name)
                    imports.append(node)

    def bindings(node):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store | ast.Del):
            return {node.id}
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            return {node.name}
        if isinstance(node, ast.Import | ast.ImportFrom):
            return {alias.asname or alias.name.split(".")[0] for alias in node.names}
        if isinstance(node, ast.arg):
            return {node.arg}
        if isinstance(node, ast.ExceptHandler) and node.name:
            return {node.name}
        if isinstance(node, ast.MatchAs | ast.MatchStar) and node.name:
            return {node.name}
        return set()

    # Conservatively refuse type aliases rebound anywhere in this file.
    shadowed = set().union(*(bindings(node) for node in ast.walk(tree) if node not in imports))
    modules -= shadowed
    classes -= shadowed

    def redis_type(annotation):
        if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
            try:
                annotation = ast.parse(annotation.value, mode="eval").body
            except (SyntaxError, ValueError):
                return False
        return (
            isinstance(annotation, ast.Name) and annotation.id in classes
        ) or (
            isinstance(annotation, ast.Attribute)
            and isinstance(annotation.value, ast.Name)
            and annotation.value.id in modules
            and annotation.attr in {"Redis", "StrictRedis"}
        )

    def local_nodes(node):
        yield node
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Lambda):
            return
        for child in ast.iter_child_nodes(node):
            yield from local_nodes(child)

    lines = []
    for function in ast.walk(tree):
        if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        args = [*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs]
        receivers = {arg.arg for arg in args if redis_type(arg.annotation)}
        nodes = [node for statement in function.body for node in local_nodes(statement)]
        receivers -= set().union(*(bindings(node) for node in nodes))
        for node in nodes:
            if (
                isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in receivers
                and node.func.attr in {"get", "set", "setex", "expire"}
            ):
                lines.append(node.lineno)
    return min(lines, default=None)


def find_evidence(
    files: list[ProjectFileSnapshot], skill: str, requirement_title: str = ""
) -> list[CodeEvidence]:
    skill = canonical_skill(skill) or skill
    results: list[CodeEvidence] = []
    seen: set[tuple] = set()
    python_scores: dict[tuple[str, int], int] = {}
    mysql_specific = (
        any(
            re.search(r"jdbc:mysql|mysql\.connector|[\"']mysql2?[\"']", _analysis_text(f), re.I)
            and PurePosixPath(f.path).suffix.lower() not in {".md", ".txt"}
            for f in files
        )
        if skill == "MySQL"
        else False
    )
    for file in files:
        normalized_path = file.path.replace("\\", "/")
        if skill in DOCUMENT_RUBRICS:
            results.extend(_document_evidence(file, skill))
            continue
        suffix = PurePosixPath(normalized_path).suffix.lower()
        if suffix in {".md", ".txt", ".pdf", ".docx", ".rst"} and not normalized_path.endswith(
            "requirements.txt"
        ):
            continue
        content = _analysis_text(file)
        detectors = DETECTORS.get(skill, ())
        if skill == "SQL":
            detectors = (
                detector(
                    "sql_schema",
                    r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?\w+\s*\(",
                    "high",
                    "存在建表实现，不代表查询优化能力",
                    r"\.sql$",
                ),
                detector(
                    "sql_query",
                    r"\bSELECT\b.+\bFROM\b",
                    "medium",
                    "存在SQL查询实现",
                    r"\.(sql|py|java|js|ts)$",
                ),
            )
        for item in detectors:
            if item.file_pattern and not item.file_pattern.search(normalized_path):
                continue
            if not item.file_pattern and suffix not in {
                ".sql",
                ".py",
                ".java",
                ".js",
                ".jsx",
                ".ts",
                ".tsx",
                ".vue",
                ".go",
                ".yaml",
                ".yml",
                ".properties",
                ".json",
                ".xml",
                ".sh",
            }:
                continue
            if (
                skill == "MySQL"
                and item.evidence_type in {"sql_schema", "sql_query"}
                and not mysql_specific
            ):
                continue
            if item.evidence_type in {"python_code", "pytest_test"}:
                # Keep a small set of implemented functions, not just the first
                # one. A helper/exception class must not hide later business
                # methods, and the ranking must remain bounded.
                anchors = (
                    [(line, 0) for line in _pytest_implementation_lines(file.content)]
                    if item.evidence_type == "pytest_test" else
                    _python_implementation_anchors(file.content, requirement_title)
                )
                if not anchors:
                    continue
                for line_number, score in anchors:
                    key = (normalized_path, item.evidence_type, line_number)
                    if key in seen:
                        continue
                    seen.add(key)
                    snippet = file.content.splitlines()[line_number - 1].strip()[:240]
                    results.append(
                        CodeEvidence(
                            skill=skill,
                            evidence_type=item.evidence_type,
                            file_path=normalized_path,
                            line_start=line_number,
                            line_end=line_number,
                            snippet=snippet,
                            strength=item.strength,
                            explanation=(
                                item.explanation + "；只评价材料支持程度，需核查本人贡献。"
                            ),
                            content_hash=hashlib.sha256(
                                file.content.encode("utf-8")
                            ).hexdigest(),
                        )
                    )
                    python_scores[(normalized_path, line_number)] = score
                continue
            if suffix == ".py" and item.evidence_type == "fastapi_route":
                matches = list(item.content_pattern.finditer(content))
                # Bounded coverage across a file, including its final route.
                if len(matches) > 6:
                    matches = [matches[round(i * (len(matches) - 1) / 5)] for i in range(6)]
                for route in matches:
                    line_number = content.count("\n", 0, route.start()) + 1
                    key = (normalized_path, item.evidence_type, line_number)
                    if key in seen:
                        continue
                    seen.add(key)
                    results.append(CodeEvidence(
                        skill=skill, evidence_type=item.evidence_type,
                        file_path=normalized_path, line_start=line_number, line_end=line_number,
                        snippet=file.content.splitlines()[line_number - 1].strip()[:240],
                        strength=item.strength, explanation=item.explanation + "；运行结果与本人贡献仍需核验。",
                        content_hash=hashlib.sha256(file.content.encode("utf-8")).hexdigest(),
                    ))
                continue
            if (normalized_path, item.evidence_type) in seen:
                continue
            match = item.content_pattern.search(content)
            if not match:
                line_number = (
                    _redis_parameter_usage_line(file.content)
                    if suffix == ".py" and item.evidence_type == "redis_usage" else None
                )
                if line_number is None:
                    continue
            else:
                match_start = match.start()
                # Several complete-line patterns deliberately include leading
                # newlines and indentation. Attribute the match to its first
                # non-blank token rather than to a preceding blank line.
                while match_start < match.end() and content[match_start].isspace():
                    match_start += 1
                line_number = content.count("\n", 0, match_start) + 1
            seen.add((normalized_path, item.evidence_type))
            snippet = file.content.splitlines()[line_number - 1].strip()[:240]
            dependency = bool(
                re.search(
                    r"dependency|config|build|gitignore|import|dockerfile|docker_compose|github_actions",
                    item.evidence_type,
                )
            )
            results.append(
                CodeEvidence(
                    skill=skill,
                    evidence_type=item.evidence_type,
                    file_path=normalized_path,
                    line_start=line_number,
                    line_end=line_number,
                    snippet=snippet,
                    strength="low" if dependency else item.strength,
                    explanation=(
                        "仅有依赖或配置声明，未据此确认功能实现。"
                        if dependency
                        else item.explanation + "；只评价材料支持程度，需核查本人贡献。"
                    ),
                    content_hash=hashlib.sha256(file.content.encode("utf-8")).hexdigest(),
                )
            )
    if skill == "Python":
        results.sort(
            key=lambda evidence: (
                STRENGTH_ORDER[evidence.strength],
                -python_scores.get((evidence.file_path, evidence.line_start), 0),
                evidence.file_path,
                evidence.line_start,
            )
        )
    else:
        results.sort(key=lambda evidence: STRENGTH_ORDER[evidence.strength])
    return results
