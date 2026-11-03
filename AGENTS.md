# AGENTS.md

## 项目约定
- 参数唯一真源是 `params/params.json`；《实施方案》那套 30 V 口径只是备选存档，不得据此改代码、BOM 或文档。
- 改参数后必须跑 `check_params.py`，全项 PASS、0 FAIL 才算完成（参数源、`param.h` 宏、merged 共享项、文档冻结文本都要同步）。
- 只做本地 commit；push 常被沙箱拦住，失败就把未推的提交列给用户，不要反复重试。
