"""Original evidence rubric; skill-map inspired hierarchy, not copied map content."""

VERSION = "skill-rubric-v1"
CRITERIA = {
    "relevance": "片段中存在与当前岗位要求直接相关的内容；名称相似不够。",
    "operation": "存在实际操作或非空实现；仅声明、依赖、函数名或 pass 不满足。",
    "task": "完整上下文展示输入、实质处理与输出，且对应当前要求；不等于运行成功。",
}

SKILL_CRITERIA = {
    "FastAPI": {
        "operation": "路由函数包含非空处理逻辑；只有装饰器、函数名或 pass 不满足。",
        "task": "完整函数展示请求输入、实质处理与明确返回或异常分支；不推断服务已运行。",
    },
    "pytest": {
        "operation": "测试函数包含针对行为结果的断言；依赖、测试名或空测试不满足。",
        "task": "完整测试展示准备、执行与有效断言；仍不能从断言存在推断测试通过。",
    },
    "索引优化": {
        "operation": "存在索引定义或执行计划分析，且与目标查询直接相关。",
        "task": "需目标查询、执行计划和优化前后对照；当前自动评级上限仍为2级。",
    },
    "备份恢复": {
        "operation": "存在明确备份或恢复命令及对象；仅工具依赖不满足。",
        "task": "需完整恢复步骤、目标环境和一致性核验；当前自动评级上限仍为2级。",
    },
    "Docker": {
        "operation": "存在有效镜像构建或服务编排配置；只有镜像名称不满足。",
        "task": "配置展示构建、运行所需依赖及服务关系；不推断镜像已成功构建。",
    },
    "CI/CD": {
        "operation": "工作流包含实际检查、构建或部署步骤；只有事件触发器不满足。",
        "task": "工作流展示触发、关键步骤和失败约束；不推断流水线已经运行通过。",
    },
    "数据库监控": {
        "operation": "存在采集数据库状态或指标的查询、命令或告警表达式。",
        "task": "需指标来源、阈值/判断与告警或处置链路；不推断线上已经部署。",
    },
}


def rubric_for(skill: str) -> dict:
    groups = {
        "数据库": ("SQL", "MySQL", "PostgreSQL", "索引优化", "备份恢复", "数据库监控", "权限管理"),
        "运维与交付": ("Linux", "Docker", "CI/CD", "Shell", "监控告警", "自动化运维"),
        "测试": ("pytest", "测试", "自动化测试"),
        "前端开发": ("React", "TypeScript", "JavaScript", "Vue"),
        "后端开发": ("Python", "FastAPI", "Java", "API"),
    }
    domain = next((name for name, skills in groups.items() if skill in skills), "岗位专项")
    note = "逐项检查证据与岗位要求的关系，不从上级领域推断其他技能。"
    if skill == "索引优化":
        note = "CREATE INDEX 只展示定义；任务完整性还需查询、执行计划与前后对比。"
    elif skill == "备份恢复":
        note = "备份命令不等于恢复；需恢复步骤、目标与一致性核验，不能假设执行成功。"
    criteria = {**CRITERIA, **SKILL_CRITERIA.get(skill, {})}
    return {"version": VERSION, "path": [domain, skill], "criteria": criteria, "note": note}
