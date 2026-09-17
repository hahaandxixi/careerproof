# 合成材料证据报告

模型：glm-4.7-flash；规则材料支持度：49.0

本文件验证后端工作流，不代表浏览器或数据库验收。未执行上传代码，人工复核待完成。

共5项岗位要求，其中4项有项目证据支撑，1项仅有简历声明，0项当前无法确认，0项暂不支持评估且不计分。分数为材料支持度，不是能力或录用结论。

降级：True；原因：provider_busy

## Python

### R1-E1

[原文件 app.py 第 12–14 行](</D:/jbcode/web ai/jianli/demo/evidence-api/app.py:12>)

已补取整个函数及装饰器原文；未执行代码，测试结果与本人贡献需人工核验

```text
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

### R1-E2

[原文件 database.py 第 4–10 行](</D:/jbcode/web ai/jianli/demo/evidence-api/database.py:4>)

已补取整个函数及装饰器原文；未执行代码，测试结果与本人贡献需人工核验

```text
def find_course(connection: psycopg.Connection, course_id: int):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, title FROM courses WHERE id = %s",
            (course_id,),
        )
        return cursor.fetchone()
```

### R1-E3

[原文件 test_app.py 第 9–12 行](</D:/jbcode/web ai/jianli/demo/evidence-api/test_app.py:9>)

已补取整个函数及装饰器原文；未执行代码，测试结果与本人贡献需人工核验

```text
def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

## FastAPI

### R2-E1

[原文件 app.py 第 12–14 行](</D:/jbcode/web ai/jianli/demo/evidence-api/app.py:12>)

已补取整个函数及装饰器原文；未执行代码，测试结果与本人贡献需人工核验

```text
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

### R2-E2

[原文件 app.py 第 2–10 行](</D:/jbcode/web ai/jianli/demo/evidence-api/app.py:2>)

局部原文，不能据此判断完整实现；运行结果和本人贡献需人工核验

```text
from pydantic import BaseModel

app = FastAPI(title="Course Task API")


class Course(BaseModel):
    id: int
    title: str

```

### R2-E3

[原文件 requirements.txt 第 1–1 行](</D:/jbcode/web ai/jianli/demo/evidence-api/requirements.txt:1>)

完整依赖声明；仅证明声明，不能证明安装、运行或功能实现

```text
fastapi==0.116.1
```

## PostgreSQL

### R3-E1

[原文件 database.py 第 4–10 行](</D:/jbcode/web ai/jianli/demo/evidence-api/database.py:4>)

已补取整个函数及装饰器原文；未执行代码，测试结果与本人贡献需人工核验

```text
def find_course(connection: psycopg.Connection, course_id: int):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, title FROM courses WHERE id = %s",
            (course_id,),
        )
        return cursor.fetchone()
```

### R3-E2

[原文件 requirements.txt 第 3–3 行](</D:/jbcode/web ai/jianli/demo/evidence-api/requirements.txt:3>)

完整依赖声明；仅证明声明，不能证明安装、运行或功能实现

```text
psycopg[binary]==3.2.9
```

## pytest

### R4-E1

[原文件 test_app.py 第 9–12 行](</D:/jbcode/web ai/jianli/demo/evidence-api/test_app.py:9>)

已补取整个函数及装饰器原文；未执行代码，测试结果与本人贡献需人工核验

```text
def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

### R4-E2

[原文件 requirements.txt 第 4–4 行](</D:/jbcode/web ai/jianli/demo/evidence-api/requirements.txt:4>)

完整依赖声明；仅证明声明，不能证明安装、运行或功能实现

```text
pytest==8.4.2
```

## Redis
