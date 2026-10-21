# Campus Signup

原创合成的本地校园活动报名服务。提供创建活动、报名、查询与取消报名接口；数据保存到调用者指定的 SQLite 文件。活动名额、报名记录与审计记录在同一事务中更新。重复报名和满额返回409，未知活动返回404，非法请求返回422，数据库故障返回503。

这是范围有限的练习项目：不提供登录鉴权、支付、邮件、分布式部署、本人贡献认证或生产服务承诺。报名取消后该学生不能再次报名同一活动；保留原报名记录，其他学生可使用释放的名额。

需要Python 3.12。在本目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m campus_signup --database ./local-data/signup.sqlite3 --port 8121
```

在 `http://127.0.0.1:8121/docs` 可操作接口：先POST `/events`（title、capacity），再POST `/registrations`（event_id、student_code）；GET接口读取已保存记录，POST `/registrations/{id}/cancel` 释放名额。重新启动时传入同一个数据库文件即可读取原记录。

`campus_signup/api.py` 负责HTTP边界；`service.py` 负责业务；`storage.py` 和 `schema.sql` 负责事务、数据约束和读取；`tests/test_registration.py` 是行为测试。运行产生的数据库、缓存、虚拟环境不属于源码材料，不应上传。
