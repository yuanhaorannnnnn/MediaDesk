# MediaDesk Ubuntu 桌面版

当前开发版面向 Ubuntu 24.04。包括首次引导、YouTube 只读账号及分批读取、有限本地目录扫描、主题列表、下载偏好与格式选择、YouTube 在线播放、本地媒体播放和音量控制、影院／全屏模式，以及设置中的深色／浅色外观。新版本的数据保存在 `${XDG_DATA_HOME:-~/.local/share}/mediadesk/`；旧实验原型 `data/` 未被修改，也不会自动迁移。

## 运行

本机已有依赖时运行：

```sh
./run-desktop.sh
```

构建 DEB：

```sh
./packaging/build-deb.sh
```

得到 `dist/mediadesk_<VERSION>_all.deb`，版本号读取自 `VERSION`。安装依赖和系统写入需要由安装环境提供相应权限。打包后通过 `mediadesk` 启动；GTK + libVLC 使用 X11，Wayland 桌面需可用的 XWayland。

首次连接 YouTube 需要 Google OAuth 桌面客户端配置，默认读取 `~/.config/youtube-readonly/client.json`；现有已授权令牌也复用该目录。可以通过 `MEDIADESK_GOOGLE_CONFIG` 调整。没有凭据时可跳过连接，手动添加链接或扫描本地文件；要连接账号须先提供自己的 Google OAuth 客户端配置。授权只请求只读 scope，浏览器 Cookie 是单独的可选下载设置。

Ubuntu 软件源中的 `yt-dlp` 版本可能过旧；程序优先使用 `MEDIADESK_YTDLP` 指定的程序，其次使用 `~/.local/share/youtube-download/bin/yt-dlp`，最后查找 PATH。用户应自行维护下载器并检查可用性。实际下载能力依赖站点、权限、网络、Node、FFmpeg 和浏览器 Keyring。

## 当前开发限制

- 暂无跨设备同步、自定义主题或自动分类；当前方案只预留扩展，数据库不是多设备同步协议。
- 下载任务可暂停、继续、编辑任务名称、删除记录和打开本地文件；删除时可选择永久删除下载目录中该视频的媒体文件和未完成文件，默认保留文件。应用关闭会中断任务，重新继续依赖 yt-dlp 对现有部分文件的恢复能力；已用本地 HTTP 和真实 yt-dlp 验证续传，来源网站及网络故障可能表现不同。
- 下载单个视频可选择自动格式或在高级格式中选择视频与音频组合。格式、大小和封面由来源实际提供。
- 在线播放使用 yt-dlp 获取临时播放地址，优先选择同时包含画面和声音的单一流；可用画质可能低于分离音视频后下载的画质。播放能力取决于来源、登录状态和网络，开始播放不会创建下载任务。
- 播放器依赖本机 libVLC、X11/XWayland 和可用音频设备。截图及 Xvfb 测试不代表真实桌面画面、声音或硬件加速已验收。
- 本项目读取 YouTube 数据及下载的组合存在平台政策限制，具体参见开发者政策；本开发版没有完成相关合规审核。
- DEB 已构建并检查包内容，尚未执行真实系统安装及干净 Ubuntu 安装测试。
