# CareerProof比赛交付专项 B1

这是独立工作树中的预审材料，产品基于e95504f，文档/源码基于f6bf1ed。未修改产品源码，未操作数据库或模型，未覆盖主工作区共享指南。最终提交待任务A完成后同步。

- [交付清单](交付清单.md)：PDF、视频脚本、源码ZIP与正式手续。
- [AI技术证据索引](AI-技术证据索引.md)：六项细则及原始证据保真副本。
- [评委快速体验指南](评委快速体验指南.md)：隔离环境与双端最短路线。
- [在线演示可行性](在线演示可行性.md)：仅评估，未部署或报价。
- [共享文档候选修订](README与指南候选修订.md)：交给主控的合并候选。
- [缺口与集成条件](缺口与集成条件.md)：真实验收与人工动作。
- [机器manifest](candidate-manifest.json)、[验收结果](evidence/validation.json)。

重新生成：使用已安装的reportlab/Pillow/pypdf、Windows等线字体运行tools/build_review_materials.py、tools/build_supporting_materials.py；校验与渲染见tools/validate_delivery.py和tools/render_review.py。网站运行不依赖这些文稿工具。PDF和素材保留原始版本，输出ZIP位于本独立worktree的output目录，不在主工作区。
