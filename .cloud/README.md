# Codex Cloud：MediaDesk

选择私有仓库 `yuanhaorannnnnn/MediaDesk`。首次配置必须选择包含本目录的支持分支或先审阅并整合支持 PR；不要在缺少本目录的旧 main 上盲目执行命令。按需要另选已发布的 `agent-skills`，不能复制本机整个配置目录或凭据。

Install script：`bash .cloud/setup.sh`。Start skill：读取 AGENTS.md，确认项目 SHA 和依赖，执行 `bash .cloud/verify.sh`，记录实际环境与检查结果。安装权限或系统版本不合适时，保留准确错误并复用同 commit 的 Ubuntu 24.04 CI，不缩水验收。

源码检查使用 Xvfb 运行完整 `test_*.py` 离线回归，不只运行旧 CI 列出的五组。数据、配置、缓存和 Google 配置使用独立临时目录；不会修改个人媒体库或真实账号。

首个任务说明：

> 为本项目完成 Codex Cloud 迁移基线。核对当前源码、AGENTS.md、测试和工具版本，执行 .cloud/verify.sh，整理真实通过、失败及未执行项。核对现有 main CI 的安装包检查及 artifact；不得把本分支测试结果混称为 main 安装包证明。不要访问个人账号、修改业务功能或自动合并 PR。交付可拉取的分支、验证证据、CI／产物链接与准确 commit。按用户授权，本地人工验收记为 deferred。环境支持时可与其他独立项目并行。

后续产品任务仍按原测试与视觉要求执行。Cloud 功能开发、CI、人工验收分别记状态；先不改任何既有定时任务。
