import type { CodeEvidence, EvidenceStrength, ProjectFile } from "../types";

/**
 * 代码静态分析器（真实规则逻辑，非 LLM）
 *
 * 设计目标：把「简历声称的能力」落到「项目代码中的可追溯证据」上。
 * MVP 阶段只做静态目录/文本分析，绝不执行用户上传的未知代码（安全隔离要求）。
 * 这层本身就是 RAG 的「检索」环节：以技能为 query，在代码语料中检索证据片段。
 */

interface Detector {
  evidenceType: string;
  contentPattern?: RegExp;
  filePattern?: RegExp;
  strength: EvidenceStrength;
  explanation: string;
}

/** 技能 → 证据检测器集合（可扩展） */
const SKILL_DETECTORS: Record<string, Detector[]> = {
  MySQL: [
    {
      evidenceType: "sql_ddl",
      contentPattern: /\bCREATE\s+TABLE\b/i,
      strength: "high",
      explanation: "存在建表 DDL，说明具备数据库结构设计能力",
    },
    {
      evidenceType: "sql_query",
      contentPattern: /\b(SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM)\b/i,
      strength: "high",
      explanation: "存在 SQL 增删改查语句，说明实际写过数据访问逻辑",
    },
    {
      evidenceType: "sql_join",
      contentPattern: /\b(INNER|LEFT|RIGHT|FULL|OUTER|CROSS)?\s*JOIN\b/i,
      strength: "medium",
      explanation: "使用 JOIN 关联查询，说明具备多表查询能力",
    },
    {
      evidenceType: "mysql_dependency",
      contentPattern: /(mysql2|mysql|sequelize|typeorm|jdbc:mysql)/i,
      filePattern: /(package\.json|pom\.xml|build\.gradle|requirements\.txt)$/i,
      strength: "high",
      explanation: "项目依赖中显式引入 MySQL 驱动/ORM",
    },
    {
      evidenceType: "mysql_config",
      contentPattern: /(jdbc:mysql|datasource|url:\s*jdbc)/i,
      filePattern: /(application.*\.(ya?ml|properties)|\.env.*)$/i,
      strength: "high",
      explanation: "配置文件中存在 MySQL 数据源连接配置",
    },
  ],
  Redis: [
    {
      evidenceType: "redis_dependency",
      contentPattern: /(redis|ioredis|jedis|lettuce)/i,
      filePattern: /(package\.json|pom\.xml|build\.gradle|requirements\.txt)$/i,
      strength: "high",
      explanation: "依赖中显式引入 Redis 客户端",
    },
    {
      evidenceType: "redis_usage",
      contentPattern: /\b(redis|Redis|cache\.(get|set)|SETEX|EXPIRE)\b/i,
      strength: "medium",
      explanation: "代码中出现缓存读写相关调用",
    },
  ],
  Java: [
    {
      evidenceType: "java_file",
      contentPattern: /\b(public|private|protected)\s+(class|interface|enum)\b/i,
      filePattern: /\.java$/i,
      strength: "high",
      explanation: "存在 Java 源文件并定义了类/接口",
    },
    {
      evidenceType: "java_build",
      contentPattern: /(maven|gradle)/i,
      filePattern: /(pom\.xml|build\.gradle)$/i,
      strength: "medium",
      explanation: "使用 Maven/Gradle 构建，说明有 Java 工程实践",
    },
  ],
  "Spring Boot": [
    {
      evidenceType: "spring_annotation",
      contentPattern: /@(SpringBootApplication|RestController|Service|Autowired|Repository)\b/i,
      strength: "high",
      explanation: "使用 Spring 核心注解，说明有框架实战",
    },
    {
      evidenceType: "spring_dependency",
      contentPattern: /spring-boot-starter/i,
      filePattern: /(pom\.xml|build\.gradle)$/i,
      strength: "high",
      explanation: "依赖中引入 Spring Boot starter",
    },
  ],
  React: [
    {
      evidenceType: "react_import",
      contentPattern: /(from\s+['"]react['"]|require\(['"]react['"]\))/i,
      strength: "high",
      explanation: "直接 import react，说明编写过 React 代码",
    },
    {
      evidenceType: "react_jsx",
      contentPattern: /\b(return\s*\(|JSX\.Element|useState|useEffect)\b/i,
      filePattern: /\.(tsx|jsx)$/i,
      strength: "high",
      explanation: "存在 JSX/函数组件与 Hooks 用法",
    },
    {
      evidenceType: "react_dependency",
      contentPattern: /("react"|"next")\s*:/i,
      filePattern: /package\.json$/i,
      strength: "medium",
      explanation: "package.json 中声明 react/next 依赖",
    },
  ],
  Vue: [
    {
      evidenceType: "vue_sfc",
      contentPattern: /(<template>|defineComponent|export\s+default\s*\{)/i,
      filePattern: /\.vue$/i,
      strength: "high",
      explanation: "存在 Vue 单文件组件",
    },
  ],
  TypeScript: [
    {
      evidenceType: "ts_file",
      contentPattern: /(:\s*(string|number|boolean|void)\b|interface\s+\w+|type\s+\w+\s*=)/i,
      filePattern: /\.tsx?$/i,
      strength: "high",
      explanation: "存在带类型标注的 TS 代码",
    },
    {
      evidenceType: "ts_config",
      contentPattern: /("compilerOptions"|"strict"\s*:)/i,
      filePattern: /tsconfig\.json$/i,
      strength: "high",
      explanation: "存在 tsconfig.json 且开启严格模式",
    },
  ],
  "Node.js": [
    {
      evidenceType: "node_import",
      contentPattern: /(require\(['"][^'"]+['"]\)|from\s+['"]node:|process\.env|express|koa)/i,
      strength: "medium",
      explanation: "使用 Node 模块/环境变量/服务端框架",
    },
    {
      evidenceType: "node_dependency",
      contentPattern: /(express|koa|fastify|nodemon)/i,
      filePattern: /package\.json$/i,
      strength: "medium",
      explanation: "依赖中引入 Node 服务端框架",
    },
  ],
  Python: [
    {
      evidenceType: "python_file",
      contentPattern: /(def\s+\w+\s*\(|import\s+\w+|from\s+\w+\s+import)/i,
      filePattern: /\.py$/i,
      strength: "high",
      explanation: "存在 Python 源文件并定义了函数/导入",
    },
    {
      evidenceType: "python_dependency",
      contentPattern: /(django|flask|fastapi|pandas|numpy)/i,
      filePattern: /requirements\.txt$/i,
      strength: "medium",
      explanation: "requirements 中声明 Python 依赖",
    },
  ],
  "REST API": [
    {
      evidenceType: "rest_route",
      contentPattern: /@(GetMapping|PostMapping|RequestMapping|app\.(get|post|put|delete)|router\.(get|post|put|delete)|@app\.route)/i,
      strength: "high",
      explanation: "定义了 HTTP 路由/接口，说明有后端接口设计能力",
    },
    {
      evidenceType: "rest_status",
      contentPattern: /\b(status\(200\)|status\(201\)|status\(404\)|\.json\(|ResponseEntity|res\.json\()/i,
      strength: "medium",
      explanation: "处理了 HTTP 状态码与响应体",
    },
  ],
  Docker: [
    {
      evidenceType: "docker_file",
      contentPattern: /\bFROM\s+\S+/i,
      filePattern: /Dockerfile/i,
      strength: "high",
      explanation: "存在 Dockerfile，说明有容器化部署能力",
    },
    {
      evidenceType: "docker_compose",
      contentPattern: /services:/i,
      filePattern: /docker-compose.*\.ya?ml$/i,
      strength: "high",
      explanation: "存在 docker-compose 编排配置",
    },
  ],
  Git: [
    {
      evidenceType: "git_ci",
      contentPattern: /(on:\s*(push|pull_request)|jobs:|steps:|- run:)/i,
      filePattern: /\.github\/workflows\/.+\.ya?ml$/i,
      strength: "high",
      explanation: "存在 GitHub Actions CI 配置，说明有版本协作与持续集成习惯",
    },
    {
      evidenceType: "git_ignore",
      contentPattern: /(node_modules|\.env|dist|target)/i,
      filePattern: /\.gitignore$/i,
      strength: "low",
      explanation: "配置了 .gitignore，具备基本版本管理意识",
    },
  ],
  数据库设计: [
    {
      evidenceType: "schema_ddl",
      contentPattern: /\b(CREATE\s+TABLE|PRIMARY\s+KEY|FOREIGN\s+KEY|UNIQUE)\b/i,
      strength: "high",
      explanation: "建表语句中包含主键/外键/唯一约束，说明有数据建模能力",
    },
  ],
  Go: [
    {
      evidenceType: "go_file",
      contentPattern: /\b(func\s+\w+|package\s+main|import\s+\()/i,
      filePattern: /\.go$/i,
      strength: "high",
      explanation: "存在 Go 源文件并定义了函数/包",
    },
  ],
  Linux: [
    {
      evidenceType: "shell_script",
      contentPattern: /^#!\/bin\/(ba)?sh|(grep|awk|sed|chmod|systemctl)\b/im,
      filePattern: /\.(sh|bash)$/i,
      strength: "medium",
      explanation: "存在 Shell 脚本，说明有 Linux 操作能力",
    },
  ],
};

/** 系统当前支持检索证据的技能标签（供岗位发布选择、简历解析等复用） */
export const KNOWN_SKILLS = Object.keys(SKILL_DETECTORS);

/** 提取命中片段：截取命中位置附近一行，并做长度限制 */
function extractSnippet(content: string, index: number): string {
  const start = Math.max(0, content.lastIndexOf("\n", index) + 1);
  const end = content.indexOf("\n", index + 1);
  const line = content.slice(start, end === -1 ? content.length : end).trim();
  if (line.length <= 160) return line;
  const rel = Math.min(index - start, Math.max(0, line.length - 160));
  return "…" + line.slice(rel, rel + 160) + "…";
}

/**
 * 在项目文件集合中检索某技能的代码证据。
 * 返回按强度排序的证据数组（去重到文件粒度）。
 */
export function findEvidence(files: ProjectFile[], skill: string): CodeEvidence[] {
  const detectors = SKILL_DETECTORS[skill];
  if (!detectors) return [];

  const results: CodeEvidence[] = [];
  const seen = new Set<string>();

  for (const file of files) {
    for (const det of detectors) {
      // 文件路径过滤（若配置）
      if (det.filePattern && !det.filePattern.test(file.path)) continue;

      if (det.contentPattern) {
        const re = new RegExp(det.contentPattern.source, det.contentPattern.flags);
        const m = re.exec(file.content);
        if (!m) continue;
        const key = `${file.path}#${det.evidenceType}`;
        if (seen.has(key)) continue;
        seen.add(key);
        results.push({
          skill,
          evidenceType: det.evidenceType,
          filePath: file.path,
          snippet: extractSnippet(file.content, m.index),
          strength: det.strength,
          explanation: det.explanation,
        });
      } else {
        // 仅路径命中（如 Dockerfile 存在）
        const key = `${file.path}#${det.evidenceType}`;
        if (seen.has(key)) continue;
        seen.add(key);
        results.push({
          skill,
          evidenceType: det.evidenceType,
          filePath: file.path,
          snippet: extractSnippet(file.content, 0),
          strength: det.strength,
          explanation: det.explanation,
        });
      }
    }
  }

  const order: Record<EvidenceStrength, number> = { high: 0, medium: 1, low: 2 };
  return results.sort((a, b) => order[a.strength] - order[b.strength]);
}
