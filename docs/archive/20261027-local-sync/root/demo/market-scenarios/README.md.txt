# 贴近岗位场景的体验材料

用户已明确：岗位发现不应堆满历史合成测试岗位。新资料收敛为三个原创场景，替代主列表中的批量验收展示；旧记录保留，不用于伪装真实招聘。

| 场景 | 岗位 | 对应材料 | 有意保留的实际缺口 |
| --- | --- | --- | --- |
| 校园活动报名服务 | Python 后端开发实习生 | event-api-resume.txt / event-api-project.zip | 数据库草案尚未接入、无并发控制及测试回执 |
| 校园活动管理台 | React 前端开发实习生 | event-console-resume.txt / event-console-project.zip | 本地数组、无接口联调与独立页面验收 |
| 会议室预约质量练习 | 接口测试开发实习生 | booking-quality-resume.txt / booking-quality-project.zip | 无并发、授权、持久化及真实团队缺陷记录 |

岗位、要求和来源在`../market-scenarios.json`；下载文件在`../../jianli/public/demo-assets/scenarios/`，原项目源码保留于本目录三个子文件夹；`assets.json`记录六份下载文件的SHA-256。所有人物、学校、企业和经历虚构；未复制真实求职者简历、企业身份、薪资或联系方式。

2026-10-19通过agent-reach体检后发现Boss专用登录通道不可用；Exa查询未返回有效对应职位。改以公开网页搜索/打开BOSS聚合页核对技术方向：

- [Python方向](https://www.zhipin.com/zhaopin/1de63f63601598543nJz3dq5/)：Python、Web、数据库与开发验证。
- [前端方向](https://www.zhipin.com/zhaopin/c075eb6d11c4af233nd539q0/)：React、TypeScript、页面与组件。
- [测试方向](https://www.zhipin.com/zhaopin/a680cb52546712fa1nF_0960/)：用例、缺陷跟踪、自动化。

这些是公开聚合页参考，不是单个职位的在招核验；具体业务、要求拆分、权重与全部材料由本项目原创编写。无BOSS账号操作、抓取简历或对真实企业发起投递。

这三套场景已于2026-10-19完成正常站接入；这是该次验收记录，不保证每个新安装环境已经初始化。新环境按使用与启动指南准备演示数据，不重复播种已有环境。

这些材料是有意保留缺口的体验片段，不是完整业务项目的能力证明。数据库草案、内存数组和接口声明不能当作持久化、事务、并发或实际运行证据；完整项目验证须另看对应项目的源码与运行记录。
