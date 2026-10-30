# MediaDesk

个人音视频工作台。`0.1.0` 面向 Ubuntu 24.04，支持本地媒体库、主题列表，以及 YouTube 和 B 站视频的导入、下载与播放。可连接一个 YouTube 账号，或在授权后读取 Chrome 中的 B 站登录状态，浏览关注和收藏。

## 安装

从 [GitHub Releases](https://github.com/yuanhaorannnnnn/MediaDesk/releases) 下载 `mediadesk_0.1.0_all.deb` 和 `SHA256SUMS`，放在同一目录。仓库为私有仓库时，需要登录具有访问权限的 GitHub 账号。

例如文件位于 `~/Downloads`：

```sh
cd ~/Downloads
sha256sum -c SHA256SUMS
sudo apt install ./mediadesk_0.1.0_all.deb
```

安装后从应用菜单打开 MediaDesk，或运行 `mediadesk`。首次引导的账号连接、扫描和下载偏好可跳过；没有账号也可以添加链接或扫描本地文件。详细依赖、账号授权、故障处理和使用说明见 [桌面版说明](README.desktop.md)。

## 卸载

```sh
sudo apt remove mediadesk
```

卸载保留用户数据，包括默认位于 `~/.local/share/mediadesk/` 的数据库和下载媒体。Google OAuth 的配置和令牌默认位于 `~/.config/youtube-readonly/`，同样保留；扫描得到的外部文件也不会随卸载删除。若设置了 `XDG_DATA_HOME`，数据目录会随之改变。

## 从源码运行

已安装依赖时可使用 `./run-desktop.sh`。构建 DEB：

```sh
./packaging/build-deb.sh
```

构建产物写入 `dist/`，版本号由 [VERSION](VERSION) 指定。Google OAuth 和浏览器 Cookie 由用户自行授权，相关凭据、媒体文件及数据库不进入仓库。

## 自动验证

GitHub Actions 在 Ubuntu 24.04 上执行离线测试，构建并安装 DEB，验证桌面程序启动和卸载，再将 DEB 和 SHA-256 校验文件作为 workflow artifact 保存。自动检查不使用个人账号，也不能替代真实桌面、声音、YouTube 网络和账号测试。

Release 手动创建；CI artifact 与 Release 互相独立。
