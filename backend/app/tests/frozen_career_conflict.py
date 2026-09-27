"""Processed synthetic fixture from the preserved v23 run1 acceptance record.

This is the saved, schema-normalized AI answer, not the provider's raw response.
Only ephemeral job IDs were replaced with a placeholder; wording is unchanged.
The source JSON stays local. No API credentials, accounts, resumes or usage rows
are included. Replaying this fixture is offline, not a new model acceptance.
"""

SOURCE_RECORD_SHA256 = "b9ea0b6aa96113ab22a05bab4988a577b64829f47bf8ede748de7445a9d44fcd"

FROZEN_DRAFT = {
    "requirements": [
        {
            "rawText": "要求使用 Python 和 FastAPI 编写查询接口",
            "skillName": "Python",
            "weight": 4,
            "isRequired": True,
            "sourceQuote": "要求使用 Python 和 FastAPI 编写查询接口",
            "sourceStart": 9,
            "sourceEnd": 37,
            "evidenceRequest": (
                "请提供使用 Python 编写的后端代码文件或代码片段，"
                "展示 Python 语法和逻辑实现。"
            ),
            "verificationQuestion": (
                "请描述你使用 Python 完成的一个后端功能，"
                "包括具体实现和遇到的挑战。"
            ),
            "weightReason": "原文明确要求使用 Python，属于核心技能，建议权重 4。",
        },
        {
            "rawText": "要求使用 Python 和 FastAPI 编写查询接口",
            "skillName": "FastAPI",
            "weight": 4,
            "isRequired": True,
            "sourceQuote": "要求使用 Python 和 FastAPI 编写查询接口",
            "sourceStart": 9,
            "sourceEnd": 37,
            "evidenceRequest": "请提供使用 FastAPI 编写的查询接口代码，展示路由定义和请求处理。",
            "verificationQuestion": (
                "请解释你如何使用 FastAPI 定义查询接口，"
                "并说明如何处理请求参数。"
            ),
            "weightReason": "原文明确要求使用 FastAPI，属于核心技能，建议权重 4。",
        },
        {
            "rawText": "包含输入校验与错误响应",
            "skillName": "输入校验",
            "weight": 3,
            "isRequired": True,
            "sourceQuote": "包含输入校验与错误响应",
            "sourceStart": 38,
            "sourceEnd": 49,
            "evidenceRequest": "请提供接口代码中实现输入校验的部分，例如参数类型检查、必填校验等。",
            "verificationQuestion": "请举例说明你在接口中如何实现输入校验，并处理校验失败的情况。",
            "weightReason": "原文明确要求包含输入校验，属于必要技能，建议权重 3。",
        },
        {
            "rawText": "包含输入校验与错误响应",
            "skillName": "错误响应",
            "weight": 3,
            "isRequired": True,
            "sourceQuote": "包含输入校验与错误响应",
            "sourceStart": 38,
            "sourceEnd": 49,
            "evidenceRequest": "请提供接口代码中定义错误响应的部分，例如状态码和错误信息格式。",
            "verificationQuestion": "请描述你如何设计接口的错误响应，包括状态码和返回体结构。",
            "weightReason": "原文明确要求包含错误响应，属于必要技能，建议权重 3。",
        },
        {
            "rawText": "提供正常和异常请求的接口测试代码及运行记录",
            "skillName": "接口测试",
            "weight": 3,
            "isRequired": True,
            "sourceQuote": "提供正常和异常请求的接口测试代码及运行记录",
            "sourceStart": 50,
            "sourceEnd": 71,
            "evidenceRequest": (
                "请提供针对接口的正常和异常请求的测试代码文件，"
                "以及测试运行记录（如日志或截图）。"
            ),
            "verificationQuestion": (
                "请说明你如何设计正常和异常请求的测试用例，"
                "并展示测试运行结果。"
            ),
            "weightReason": "原文明确要求提供接口测试代码及运行记录，属于必要技能，建议权重 3。",
        },
    ],
    "model": "deepseek-flash",
    "usage": None,
    "confirmed": False,
}

FROZEN_PLAN = {
    "comparison": (
        "本次只给出一个岗位：合成后端实习岗位，方向为软件后端。"
        "没有其他岗位可比较，因此不存在方向差异或岗位要求差别。"
        "当前材料中可见的证据是：在 app.py 中有一个使用 FastAPI "
        "装饰器绑定的 /health 路由，函数内对 name 做了空值判断并抛出 400 错误，"
        "返回状态和名称。这能支持“使用 Python 和 FastAPI 编写查询接口”的部分可见事实，"
        "但输入校验与错误响应、接口测试代码及运行记录在材料中尚未展示，"
        "需要人工核对或补充。"
    ),
    "focusJobId": "__synthetic_job__",
    "advice": [
        {
            "jobId": "__synthetic_job__",
            "reason": (
                "岗位要求使用 Python 和 FastAPI 编写查询接口，并包含输入校验、"
                "错误响应以及正常和异常请求的接口测试代码及运行记录。"
                "当前材料中可见 app.py 里有一个 FastAPI 路由绑定和简单的空值校验，"
                "能部分对应 Python 和 FastAPI 的要求；但输入校验与错误响应、"
                "接口测试及运行记录在材料中尚未展示，规则也暂不能判断，需要人工核对。"
            ),
            "keyGap": (
                "当前材料未展示完整的输入校验与错误响应实现，"
                "也未展示正常和异常请求的接口测试代码及运行记录。"
            ),
            "nextTask": (
                "补交一份可核验的接口测试与运行记录，覆盖正常请求和异常请求，"
                "并附上对应的输入校验与错误响应代码片段。"
            ),
            "taskPlan": {
                "deliverable": "一份接口测试文件（如 "
                "test_app.py）和一份运行记录（如终端输出或测试报告截图），以及对应的输入校验与错误响应代码片段。",
                "steps": [
                    "在现有 FastAPI "
                    "项目中补充或确认输入校验与错误响应逻辑，例如对必填参数缺失、空值等情况返回明确的错误状态和说明。",
                    "编写接口测试代码，至少包含一个正常请求用例和一个异常请求用例，分别验证成功返回和错误响应。",
                    "运行测试并保存运行记录，记录中应能看出测试命令、用例名称和通过/失败结果。",
                    "将测试文件、运行记录和对应代码片段整理为可提交的材料。",
                ],
                "acceptanceChecks": [
                    "提供测试文件内容，其中能看到正常请求和异常请求的测试用例。",
                    "提供运行记录，其中能看到测试命令和每个用例的执行结果。",
                    "提供输入校验与错误响应的代码片段，能对应到具体路由和处理逻辑。",
                ],
            },
            "citationIds": ["J1-E1", "J1-E2"],
        }
    ],
}
