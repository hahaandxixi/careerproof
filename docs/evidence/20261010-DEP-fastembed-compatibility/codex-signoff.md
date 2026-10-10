# 首批依赖嵌入兼容性独立签收

2026-10-10。ZCode24原始README、容差声明、探针与130项受影响回归原样保留；Codex对现行升级环境独立重跑新兼容测试，codex-signoff.raw.out为3通过、0跳过，实际调用本地CPU ONNX，不使用替身或网络模型。

比较器原JSON中两个minCosine键分别意图表示阈值与实测值，后者覆盖前者；这没有改变原布尔判定，但丢失了阈值证据。现将它们显式分列minimumCosineThreshold及observedMinimumCosine；容差数值不变，comparison-codex.json为新签收结果。原comparison.json及ZCode交付时的哈希表仍保留，旧哈希不代表修正后的比较器。

两份原探针输入重比：同5个权重哈希、6×384、最大绝对差0，余弦最小0.9999999999999998（门槛0.999999999），查询排序与范数一致。此结论证明本轮合成输入下的跨版本数值兼容，不冒充检索质量提升或全依赖无漏洞。

fastembed/Pillow首批兼容补强可签收；框架/前端/其余依赖仍以各自已提交处置证据为准。braces及selector-parser残余风险不因这个测试消失，P2暂停不变。
