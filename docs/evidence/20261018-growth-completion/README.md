# 10/18 正常站补证新版与分段视频

运行源码c8868aa，普通3000/8000与原业务库；使用已有合成学生/项目/任务，不创建真实投递，不发外部模型请求。沿10/17未完成现场续办，不新建同名项目、不重复上传。

## 实际链路

- 已有任务0c67132f-f355-4819-819f-29b8529afa9e，基准报告1b6c0425-848a-4229-8cc8-cc4d4447ba54。10/17录制已保存计划并给原CP01视频项目上传v2；本轮通过实际选择器确认该项目已有两版，v2已解析，所以没有再上传。
- 保留原简历v1（2a860b9c…），移除项目v1选择、选同一项目的v2（b37f9ebf-eb59-4fec-a147-0fb85d287af1），点击保存。材料hash与合成ZIP的8e37e50c…一致。
- 外部AI授权未勾选，明确点击生成新报告一次。新任务634250aa-3876-4a40-a790-66c6e91803a7完成，新报告bf856aaa-7be2-4883-9517-fb1791bd0a5a保存。
- 任务逐项对比显示Redis从仅自述/未评级→局部操作，其他四项等级不变但部分来源变化；新增redis_cache.py第5—10行，setex/get静态调用可定位。未执行源码，不证明实际运行、本人贡献或能力提升。
- 原投递b756d9c2…仍replied，仍固定报告1b6c…；当前应用页面清楚显示“后续新报告不会替换本次投递”。本轮没有撤回、重新投递、回复或标通知已读。

## 独立只读核对

before/after.json公共表摘要对照：仅agent_steps、analysis_tasks、evidence_growth_tasks、evidence_sources、match_items、match_reports、skill_evidence变化，与新报告和选择保存相符。applications、application_events、notifications、ai_request_attempts和ai_usage_logs全部计数/内容摘要不变；这些表也与10/17创建补证任务前的normal-before.json一致。

verify_saved_growth.py使用REPEATABLE READ、READ ONLY，仅查询指定合成记录；断言原投递绑定原基准、原状态、新任务completed、新报告mode=rules/provider=null/skippedReason=consent_not_granted、外发同意false。原投递快照SHA256在saved-result.json，不复制原快照正文。存储growth.status仍analyzing，服务读取时依完成报告派生compared；不是未完成分析。

核对脚本初次误以为growth存储状态应为completed，第二次误以为报告metadata.provider应为rules（实际规则provider存null，AgentStep才存rules）。核对服务实现后纠正了这两处验证假设，未改业务数据/代码，不把脚本错误解释成产品故障。任务选择器首次exact-text未命中，改用已观测summary后成功；没有重复提交。

## 视频草稿

本机output/video/CareerProof-chain-and-growth-20261018-r1.mp4，261.36秒（4分21秒）、35段、968张真实网页帧，约6.29MB，H264/1920x1080/25fps，无音轨。原生采集1265x712且变帧率，编码放大/补重复帧，不宣称原生1080p25录屏。SHA256：0ef7352b79f86ccfd543d16764db2bd223c1a3063bc894237f4a95f63e383a72。

组合10/16双端链23段、10/17补证计划/新版上传4段和10/18选择/新报告/变化/原投递8段；跨日期/源码版本，标题与持续字幕明确分段与限制。10/17的失败入口片段01和超时片段04排除，失败原素材仍保留。生成器未改、不生成网页画面；片头片尾仅解释覆盖范围。

ffprobe格式检查、全片解码退出0，Redis段实际编码帧目检确认引用与字幕可读。没有完整人工逐秒回放，仍需配音及最终审片。字幕SRT在同名视频旁，captions.md为配音改稿基础，不等同已配音。

本机capture-20261016-upload-chain、capture-20261017-growth、capture-20261018-growth为原帧；capture-20261018-combined只保存索引/故事文件，build-20261018-combined-r1是转码中间件。MP4/原帧均在ignored output/video，不随Git源码包自动带走；提交前需单独复制/上传。video-build.json与video-summary.json保存指纹和范围，video-redis-frame.png为实际成片抽帧。

## 剩余范围

### 同日后续：离线合成普通话配音草稿

新文件`output/video/CareerProof-voiced-draft-20261018-r1.mp4`，实际382.061016秒（6分22秒）、12,005,643字节，H264 1920×1080/25fps＋AAC 48kHz单声道。SHA256为`8b615651f363fe3dbcdb672508c722e1ccba418356c4f8441a9eddb7e1330a82`。旧4分21秒无声稿、原帧与转码中间件均保留。

使用本机System.Speech的Microsoft Huihui Desktop（zh-CN、rate=0），没有把文本/音频上传到语音服务，没有克隆真人声音。35段原实录重新叠加如实的“合成配音/低帧率/非冻结”边界，新增项目介绍、工作流说明和结尾三张解释卡。配音文本见narration-draft.json/captions.md；素材为10/16—18跨日期版本，模型演示仍为规则路径，不把工作流介绍讲成真实调用结果。

执行：`backend/.venv-dependency23/Scripts/python.exe scripts/build_narrated_demo.py --capture-dir output/video/capture-20261018-combined --manifest docs/evidence/20261018-growth-completion/narration-draft.json --work-dir output/video/build-20261018-voiced-r1 --output output/video/CareerProof-voiced-draft-20261018-r1.mp4`。原始合成/编码日志、WAV、38段计划均留在该ignored工作目录。全片ffmpeg解码退出0、错误日志为空；格式/音轨已核，响度检测有非静音信号（均值-24.4dB、峰值-0.5dB），不等同听感合格。四个实际编码关键帧目检、voiced-contact-sheet.jpg；没有完整人工试听、逐句同步或口音评价。

35段实录合计末帧延长约23.15秒，最长单段3.06秒；不加快/改写实际操作。片头、技术说明、片尾按实际旁白长度显示，所有时长见voiced-summary.json；原素材低帧率且编码放大，不宣称原生1080p录屏。Ruff首轮发现未使用subprocess导入，移除后通过；PowerShell helper语法检查通过。未启停网站、未操作数据库。

本稿已具备所列时长/编码/音轨，但仍需团队完整审片、确认合成讲解使用、补入新鲜真实AI证据并与冻结版本同步。不能据此宣布正式视频交付或赛事审核通过。MP4/WAV/原始素材不随Git源码包带走，须另行备份。

跨日更新：本稿生成后，10/18 23:57—58用户授权的首批三例真实AI已完成，结果见70号目录。视频片尾“待授权”是生成时状态，尚未把该批结果补录入画面/配音，最终稿应替换，不能把本稿口播当10/19最新进度。

本轮证明开发者沿已有合成现场完成新版链路，不是独立首次使用者验证，也不是从空库同一版本连续录制。真人首次用户、真实AI语义质量、配音/赛事格式/最终候选、PDF/源码包/评审访问/签署/第三方许可仍待。此次未修改源码、不清理任何临时目录，网站保持运行。
