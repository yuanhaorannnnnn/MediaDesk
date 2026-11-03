# MediaDesk 工作规则

用简体中文沟通；命令、路径与标识符保留英文。先读 README.md、README.desktop.md、DESIGN.md 和当前任务，再操作。

## 工作与交付

- 只修改当前获准范围。保留其他人的修改，不 reset、clean、stash、force-push 或批量暂存。
- 在独立分支交付可审阅变更。代码、离线测试、真实桌面、账号行为和发布状态分别报告。
- 本项目是 Ubuntu 桌面产品。Cloud 的自动检查不能替代真实播放、声音、账号登录和安装体验。
- 当前 Cloud 迁移允许先跳过本地人工验收，必须记为 deferred，不能记为 pass。
- 不读取个人媒体库、浏览器 Cookie、OAuth 配置、密钥库或真实账号，不把它们写入 fixture、日志或仓库。账号操作和对外发送需要相应任务授权。
- 产品发布包由主分支和集成 owner 负责；Cloud 功能分支不擅自打包发布。复用 main 的 CI 下载已验证包时记录准确 commit。

## 验证入口

- Cloud 环境安装：`bash .cloud/setup.sh`。
- 源码离线验证：`bash .cloud/verify.sh`，使用独立临时 XDG 数据目录。
- 完整 Ubuntu 24.04 安装包验证以 `.github/workflows/ci.yml` 为准，不省略失败项后宣布通过。
- 视觉修改遵循 DESIGN.md，保留专业视觉工具和独立评审要求；工具不可用则报告缺口，不用普通自审冒充。

## 上下文与成果

不要假定 `/home/yhr`、`/media/yhr/2T`、本地全局 skills 或 Canon 自动存在。以当前 checkout 为项目根。只有当前环境实际提供的 skills、脚本和工具才算可用。

交付说明包含 base／结果 commit、变更路径、实际运行的检查、失败及未运行项、成果入口及 SHA256、本地验收 deferred 与后续步骤。Cloud VM 不是长期成果存储。
