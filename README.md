# MediaDesk

个人音视频工作台。当前开发版面向 Ubuntu 24.04 和单个 YouTube 账号，支持媒体库、主题列表、视频下载、本地播放和在线播放。

## 运行和安装

详细依赖、账号授权和本地运行方法见 [桌面版说明](README.desktop.md)。构建 DEB：

```sh
./packaging/build-deb.sh
```

构建产物写入 `dist/`。版本号由 [VERSION](VERSION) 统一指定。安装后从应用菜单或运行 `mediadesk` 启动。

用户数据默认保存在 `~/.local/share/mediadesk/`；卸载应用不会删除这些数据。Google OAuth 和浏览器 Cookie 由用户自行授权，相关凭据、媒体文件及数据库不进入仓库。

## 自动验证

GitHub Actions 在 Ubuntu 24.04 上执行离线测试，构建并安装 DEB，验证桌面程序启动和卸载，再将 DEB 和 SHA-256 校验文件作为 workflow artifact 保存。自动检查不使用个人账号，也不能替代真实桌面、声音、YouTube 网络和账号测试。

项目目前没有自动发布流程；只有明确决定发布后才会创建 GitHub Release。
