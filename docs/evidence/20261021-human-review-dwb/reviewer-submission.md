# 当前生产提示词：首批三例人工核对表

来源：2026-10-18真实DeepSeek调用；全部为合成材料。人工语义评审仍为0/3，未代填。请先阅读[独立人工复核指南的统一rubric](REVIEWER-GUIDE.md#统一-rubric)，再独立核对本表的输入、引用映射和模型原文。隐藏参考答案、实现方判断、助手初查及其他评审结果，不将其作为评审依据。程序校验结果不是人工答案。无需运行任何代码。

请分别填写：引用与结论是否受支持；是否识别空实现/矛盾；有无夸大运行、贡献或能力；建议是否可执行。无法判断请写明，不猜测，不代签。

## 样本 M01

岗位要求：提供 FastAPI 健康检查接口的实现材料

简历声明：使用 FastAPI 编写健康检查

材料文件：`app.py`
```text
from fastapi import FastAPI
app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}
```


模型可用的引用映射（发送时原文）：

`R1-E1` → `app.py` 第4—6行
```text
@app.get("/health")
def health():
    return {"status": "ok"}
```

`R1-E2` → `app.py` 第1—6行
```text
from fastapi import FastAPI
app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}
```
模型输出（原文）：
```json
{
  "summary": "材料展示 app.py 中 FastAPI 应用实例与 /health 路由，函数返回固定状态字典；当前引用已覆盖该函数及整文件。未展示运行结果、测试记录或本人贡献，无法确认接口实际可用。",
  "items": [
    {
      "requirement_id": "4e681c30-89da-565f-8338-6dfe7dd044ff",
      "explanation": "片段可见 FastAPI 应用实例和 /health 路由，函数返回 {\"status\": \"ok\"}，属于与健康检查直接相关的非空处理逻辑；当前引用已覆盖该函数原文及整文件。",
      "citation_ids": [
        "R1-E1",
        "R1-E2"
      ],
      "information_gap": "未展示接口运行结果、测试请求与断言记录，也未展示本人贡献说明。",
      "suggestion": "提交 /health 的请求响应记录或测试输出，并附具名贡献说明，核对接口实际返回与作者归属。",
      "task_plan": {
        "deliverable": "/health 接口的请求响应记录或测试输出，附具名贡献说明",
        "steps": [
          "整理对 /health 发起请求后得到的响应内容",
          "补充说明该文件由谁编写及具体负责部分"
        ],
        "acceptance_checks": [
          "响应记录显示状态码与返回体",
          "贡献说明能对应到 app.py 的具体内容"
        ]
      },
      "confidence": 0.8,
      "rating": {
        "level": 3,
        "reason": "可见 FastAPI 应用与 /health 路由，函数有明确返回；完整任务实现由当前函数原文支持，运行与贡献仍未知。",
        "criteria": [
          {
            "criterion": "relevance",
            "supported": true,
            "citation_ids": [
              "R1-E1",
              "R1-E2"
            ],
            "reason": "片段含 FastAPI 应用与 /health 路由，直接对应健康检查要求。"
          },
          {
            "criterion": "operation",
            "supported": true,
            "citation_ids": [
              "R1-E1"
            ],
            "reason": "路由函数返回非空状态字典，存在实质处理逻辑。"
          },
          {
            "criterion": "task",
            "supported": true,
            "citation_ids": [
              "R1-E1",
              "R1-E2"
            ],
            "reason": "当前引用覆盖完整函数与整文件，展示路由定义及明确返回。"
          }
        ]
      }
    }
  ],
  "model": "deepseek-flash",
  "usage": {
    "input_tokens": 3225,
    "output_tokens": 461,
    "cache_hit_tokens": 0,
    "latency_ms": 2801
  }
}
```

| 核对项 | 结论（通过／不通过／无法判断） | 理由、原句与文件/行号 |
| --- | --- | --- |
| 引用是否支持结论 | 不通过 | "材料展示 app.py 中 FastAPI 应用实例与 /health 路由，函数返回固定状态字典；当前引用已覆盖该函数及整文件。未展示运行结果、测试记录或本人贡献，无法确认接口实际可用。",但是我觉得这已经可以检查接口是接通了,具体的实现失败是函数的问题 |
| 是否识别空实现或矛盾 | 不通过 | 我认为这不是空实现,已经确保了连通后端 |
| 是否避免夸大运行、贡献或能力 | 待填写 | 待填写 |
| 建议是否具体可执行 | 待填写 | 待填写 |

## 样本 M02

岗位要求：实现可返回业务结果的 FastAPI 接口

简历声明：已完整实现 FastAPI 业务接口

材料文件：`app.py`
```text
from fastapi import FastAPI
app = FastAPI()
@app.get("/tasks")
def tasks():
    pass
```


模型可用的引用映射（发送时原文）：

`R1-E1` → `app.py` 第3—5行
```text
@app.get("/tasks")
def tasks():
    pass
```

`R1-E2` → `app.py` 第1—5行
```text
from fastapi import FastAPI
app = FastAPI()
@app.get("/tasks")
def tasks():
    pass
```
模型输出（原文）：
```json
{
  "summary": "材料显示 app.py 中定义了 FastAPI 应用和 /tasks 路由，但路由函数体为 pass，未展示业务处理或返回结果；简历声称已完整实现业务接口，与可见实现存在差异。",
  "items": [
    {
      "requirement_id": "c373f24f-8055-5f11-a3f0-c9b4a74bbb8a",
      "explanation": "片段可见 FastAPI 应用实例与 /tasks 路由装饰器，但函数体仅为 pass，未展示业务处理或返回结果；简历声称已完整实现业务接口，与可见实现存在差异。",
      "citation_ids": [
        "R1-E1",
        "R1-E2"
      ],
      "information_gap": "未展示路由的业务处理、返回结果及运行验证记录，本人贡献也无法由静态材料确认。",
      "suggestion": "提交包含具体业务处理与返回结果的接口实现文件，并附运行或测试记录以核对实际响应。",
      "task_plan": {
        "deliverable": "包含业务处理与明确返回的 /tasks 接口实现文件及对应运行记录",
        "steps": [
          "补充展示 /tasks 路由函数中读取或构造业务数据并返回响应的实现",
          "提供调用该接口的运行记录或测试输出"
        ],
        "acceptance_checks": [
          "路由函数体包含非空处理逻辑并返回明确结果",
          "运行记录显示接口返回与实现一致的业务数据"
        ]
      },
      "confidence": 0.9,
      "rating": {
        "level": 1,
        "reason": "存在 FastAPI 路由线索，但函数体为 pass，未展示业务处理与返回，完整任务实现未知。",
        "criteria": [
          {
            "criterion": "relevance",
            "supported": true,
            "citation_ids": [
              "R1-E1",
              "R1-E2"
            ],
            "reason": "片段包含 FastAPI 应用与 /tasks 路由定义，与要求直接相关。"
          },
          {
            "criterion": "operation",
            "supported": false,
            "citation_ids": [
              "R1-E1"
            ],
            "reason": "路由函数体仅为 pass，未展示非空处理逻辑。"
          },
          {
            "criterion": "task",
            "supported": false,
            "citation_ids": [
              "R1-E1"
            ],
            "reason": "未展示请求输入、实质处理与明确返回或异常分支。"
          }
        ]
      }
    }
  ],
  "model": "deepseek-flash",
  "usage": {
    "input_tokens": 3212,
    "output_tokens": 452,
    "cache_hit_tokens": 2432,
    "latency_ms": 3023
  }
}
```

| 核对项 | 结论（通过／不通过／无法判断） | 理由、原句与文件/行号 |
| --- | --- | --- |
| 引用是否支持结论 | 通过 | "材料显示 app.py 中定义了 FastAPI 应用和 /tasks 路由，但路由函数体为 pass，未展示业务处理或返回结果；简历声称已完整实现业务接口，与可见实现存在差异。" |
| 是否识别空实现或矛盾 | 通过 | "材料显示 app.py 中定义了 FastAPI 应用和 /tasks 路由，但路由函数体为 pass，未展示业务处理或返回结果；简历声称已完整实现业务接口，与可见实现存在差异。" |
| 是否避免夸大运行、贡献或能力 | 待填写 | 待填写 |
| 建议是否具体可执行 | 待填写 | 待填写 |

## 样本 M03

岗位要求：提供筛选正数并求和的 Python 实现

简历声明：Python 函数 sum_positive 已实现筛选正数并求和

材料文件：`maths.py`
```text
def sum_positive(values):
    return 0
```


模型可用的引用映射（发送时原文）：

`R1-E1` → `maths.py` 第1—2行
```text
def sum_positive(values):
    return 0
```
模型输出（原文）：
```json
{
  "summary": "材料仅含一个两行函数，函数体固定返回 0，未展示筛选正数或求和逻辑，与简历自述矛盾。",
  "items": [
    {
      "requirement_id": "7857f7e9-7aee-55b4-82e4-d63fe4d26bd4",
      "explanation": "片段显示 sum_positive 函数体只有 return 0，未展示筛选正数或累加求和；简历声称已实现筛选正数并求和，与可见实现不一致。",
      "citation_ids": [
        "R1-E1"
      ],
      "information_gap": "未展示筛选正数与求和的实现，也未提供运行结果或本人贡献记录。",
      "suggestion": "提交包含筛选正数与求和逻辑的新版本函数文件，并附可核验的运行输出或测试记录。",
      "task_plan": {
        "deliverable": "修改后的 sum_positive 实现文件及对应运行记录",
        "steps": [
          "提交含筛选正数与累加逻辑的新版本 maths.py",
          "提供该版本的运行输出或测试记录"
        ],
        "acceptance_checks": [
          "新版本函数体可见对正数的筛选与求和",
          "运行记录显示对含负数输入的期望输出"
        ]
      },
      "confidence": 0.9,
      "rating": {
        "level": null,
        "reason": "函数体固定返回 0，未展示筛选或求和操作，三项判据均无证据支持。",
        "criteria": [
          {
            "criterion": "relevance",
            "supported": false,
            "citation_ids": [
              "R1-E1"
            ],
            "reason": "函数名与要求相关，但函数体未展示筛选正数或求和内容。"
          },
          {
            "criterion": "operation",
            "supported": false,
            "citation_ids": [
              "R1-E1"
            ],
            "reason": "函数体仅 return 0，未展示任何实质处理操作。"
          },
          {
            "criterion": "task",
            "supported": false,
            "citation_ids": [
              "R1-E1"
            ],
            "reason": "未展示输入筛选、求和处理与输出对应的完整实现。"
          }
        ]
      }
    }
  ],
  "model": "deepseek-flash",
  "usage": {
    "input_tokens": 3059,
    "output_tokens": 402,
    "cache_hit_tokens": 2432,
    "latency_ms": 2186
  }
}
```

| 核对项 | 结论（通过／不通过／无法判断） | 理由、原句与文件/行号 |
| --- | --- | --- |
| 引用是否支持结论 | 通过 | 材料仅含一个两行函数，函数体固定返回 0，未展示筛选正数或求和逻辑，与简历自述矛盾。 |
| 是否识别空实现或矛盾 | 识别 | "片段显示 sum_positive 函数体只有 return 0，未展示筛选正数或累加求和；简历声称已实现筛选正数并求和，与可见实现不一致。" |
| 是否避免夸大运行、贡献或能力 | 待填写 | 待填写 |
| 建议是否具体可执行 | 待填写 | 待填写 |

“无法判断”也须逐项说明缺少什么；材料中没有空实现或矛盾时，说明本项是否适用及理由，不为凑结论编造问题。

## 汇总与确认

评审者：____邓文博___　日期：___2026.10.21____
实际核对数量：_____3____
主要问题与是否需要返工：______不需要____

本表未填写不代表通过；不由模型或脚本填写人工结论。
