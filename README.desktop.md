# MediaDesk Ubuntu 桌面版

当前开发版面向 Ubuntu 24.04。包括首次引导、YouTube 只读账号及分批读取、YouTube 和 B 站单视频导入、在线播放与下载、有限本地目录扫描、主题列表、下载偏好与格式选择、本地媒体播放和音量控制、影院／全屏模式，以及设置中的深色／浅色外观。新版本的数据保存在 `${XDG_DATA_HOME:-~/.local/share}/mediadesk/`；旧实验原型 `data/` 未被修改，也不会自动迁移。

外观提供深色、浅色，以及从纳比派平面色块和新印象主义相邻色触转译的两套主题；设置会保留在本机，封面本身不会被染色。

侧栏「关注」和「收藏与播放列表」按来源显示 YouTube 与 B 站内容，可切换全部平台或单个平台。设置中的账号卡片会在打开时验证连接，也可手动刷新；网络错误显示为无法验证，保留最近一次成功验证时间。B 站账号验证需要先允许读取 Chrome 登录状态。

## 前置条件与依赖

- **系统与桌面：** Ubuntu 24.04 桌面，X11 或可用的 XWayland；其他 Ubuntu 版本尚未验证。播放需要可用的音频设备。
- **网络：** 安装时需要访问 GitHub 和已配置的 Ubuntu 软件源；连接账号、读取平台内容、在线播放和下载时需要访问相应平台。网络连通性及访问方式由使用环境决定。
- **安装权限：** 使用 `apt` 安装系统包需要管理员权限。`apt` 会从已配置的软件源安装 DEB 的必需依赖；不需要提前逐个手动安装下表的包。具体可用版本取决于软件源，MediaDesk 不固定或备份这些系统包的版本。

| 依赖包 | 用途 |
| --- | --- |
| `python3`、`python3-gi`、`gir1.2-gtk-3.0`、`gir1.2-gdkpixbuf-2.0`、`librsvg2-common` | Python 运行环境、GTK 桌面界面、图片和 SVG 图标。 |
| `libvlc5`、`vlc-plugin-base`、`vlc-plugin-video-output` | 音视频播放和画面输出；无需单独安装 VLC 桌面应用。 |
| `ffmpeg` | 音视频处理以及下载后的媒体检查，包括 `ffprobe`。 |
| `yt-dlp` | 解析支持的来源、获取播放地址和下载媒体；网站变化可能要求更新版本。 |
| `python3-requests`、`python3-google-auth`、`python3-google-auth-oauthlib` | 网络请求和 Google OAuth 账号连接。 |
| `python3-secretstorage` | 访问支持的桌面密钥环，供授权后的浏览器登录状态读取使用。 |
| `xdg-user-dirs` | 识别桌面的标准用户目录。 |

`nodejs` 是 DEB 的**推荐依赖**，不是必需依赖。`apt` 通常会安装推荐包，但也可能因本机配置被省略。部分 YouTube 内容需要 yt-dlp 支持的 JavaScript 运行时；MediaDesk 在检测到 Node.js 和相应 yt-dlp 选项时会启用 Node.js。兼容性取决于实际使用的 yt-dlp、运行时和相关组件版本：例如当前 [yt-dlp EJS 的运行时要求](https://github.com/yt-dlp/ejs#runtime-requirements)列出 Node.js 22 或更新版本，而软件源提供的版本可能不同。更多信息见 [yt-dlp 依赖说明](https://github.com/yt-dlp/yt-dlp#dependencies)。

连接 YouTube 账号还需要自行准备 Google OAuth 客户端配置；读取 B 站账号需要已登录的 Chrome 和用户授权。这些是对应账号功能的条件，不是安装 MediaDesk 的条件。详见[账号和下载](#账号和下载)。

## 安装、启动和卸载

### curl 安装

在 Ubuntu 24.04 的终端中，先准备 `curl`、`gh` 和 `sudo`，并使用 `gh auth login` 登录可访问本私有仓库的 GitHub 账号。随后执行：

```sh
bash -c 'set -eo pipefail; f=$(mktemp); trap '\''rm -f -- "$f"'\'' EXIT; gh auth token | { IFS= read -r token; printf "header = \"Authorization: Bearer %s\"\n" "$token"; } | curl -fsSL --config - -H "Accept: application/vnd.github.raw+json" "https://api.github.com/repos/yuanhaorannnnnn/MediaDesk/contents/packaging/install-release.sh?ref=main" -o "$f"; sh "$f"'
```

命令通过已登录的 `gh` 向 GitHub 认证，先完整取得安装脚本再执行；管理员密码仅在终端中输入。脚本默认安装已发布的 `v0.1.0`：下载 DEB 和校验文件，校验 SHA-256、包名、版本与架构，然后由 `apt` 复用满足包约束的现有依赖并安装缺失依赖。DEB 当前未声明依赖的最低版本；媒体平台和 yt-dlp 可能另有版本兼容要求，见[前置条件与依赖](#前置条件与依赖)。

当前脚本安装的是已发布的 Release，未发布的主分支修改不会包含在内。

### 手动安装

在 Ubuntu 24.04 桌面，从 [GitHub Releases](https://github.com/yuanhaorannnnnn/MediaDesk/releases) 下载 `mediadesk_0.1.0_all.deb` 和 `SHA256SUMS` 到同一目录。私有仓库需要登录有访问权限的 GitHub 账号。以下载到 `~/Downloads` 为例：

```sh
cd ~/Downloads
sha256sum -c SHA256SUMS && sudo apt install ./mediadesk_0.1.0_all.deb
```

校验通过时显示 `mediadesk_0.1.0_all.deb: OK`；校验失败请重新下载，不要继续安装。`apt` 从已配置的软件源安装所需依赖。若同版本已安装，想重新安装下载的包，可使用 `sudo apt install --reinstall ./mediadesk_0.1.0_all.deb`。如果 `apt` 提示已有软件存在未满足依赖，请先阅读它给出的修复方案；修复其他软件包可能会产生安装或卸载操作。

从应用菜单启动 MediaDesk，或在终端运行：

```sh
mediadesk
```

开发版中，下载任务处于等待、下载中或暂停时，关闭窗口默认会询问是否最小化、退出并中断或取消；可以在设置中调整。最小化会保留应用进程，暂停的任务仍需手动继续。没有这些任务时关闭窗口会退出应用。已发布的 0.1.0 尚不包含该设置。

如果安装后应用列表仍显示默认齿轮，可以先检查图标文件和桌面会话。曾在 Ubuntu X11 会话中观察到重启 GNOME Shell 后图标恢复；操作前请保存工作，其他环境尚未验证。

程序使用 GTK + libVLC 和 X11；在 Wayland 桌面上需要可用的 XWayland。`0.1.0` 以 Ubuntu 24.04 为基线，其他系统或版本未验证。

卸载程序：

```sh
sudo apt remove mediadesk
```

卸载不会删除 `${XDG_DATA_HOME:-~/.local/share}/mediadesk/` 下的数据库和下载媒体，也不会删除用户扫描的外部文件或 `~/.config/youtube-readonly/` 下的 Google OAuth 配置和令牌。请在需要清理数据时先自行检查这些目录的内容。

## 从源码运行

本机已有依赖时运行：

```sh
./run-desktop.sh
```

构建 DEB：

```sh
./packaging/build-deb.sh
```

得到 `dist/mediadesk_<VERSION>_all.deb`，版本号读取自 `VERSION`。安装依赖和系统写入需要相应权限。

## 账号和下载

首次连接 YouTube 需要 Google OAuth 桌面客户端配置，默认读取 `~/.config/youtube-readonly/client.json`；现有已授权令牌也复用该目录。可以通过 `MEDIADESK_GOOGLE_CONFIG` 调整。没有凭据时可跳过连接，手动添加链接或扫描本地文件；要连接账号须先提供自己的 Google OAuth 客户端配置。授权只请求只读 scope，浏览器 Cookie 是单独的可选下载设置。

设置中的“断开连接”停止 MediaDesk 发起新的 YouTube 账号读取，并保留本地媒体和共享令牌；已开始的读取可能继续，其他使用该令牌的应用不受影响。重新连接可能复用已有令牌，不提供账号切换或撤销 Google 授权。B 站断开只关闭关注和收藏的 Chrome 登录状态读取，不退出 Chrome；播放与下载的 Cookie 选项需单独设置。

Ubuntu 软件源中的 `yt-dlp` 版本可能过旧；程序优先使用 `MEDIADESK_YTDLP` 指定的程序，其次使用 `~/.local/share/youtube-download/bin/yt-dlp`，最后查找 PATH。用户应自行维护下载器并检查可用性。实际下载能力依赖站点、权限、网络、Node、FFmpeg 和浏览器 Keyring。

播放时默认按空格切换播放和暂停；设置中可改为 K 或关闭。输入框及其他有键盘操作的控件获得焦点时，保留控件原有操作。

B 站账号读取使用上述 yt-dlp 脚本的 Python 环境读取 Chrome Cookie；旧版 yt-dlp 可能无法识别新版 Chrome 的登录状态，遇到此情况请更新 yt-dlp。账号读取仅在用户允许后进行，可在设置中关闭。

## 当前开发限制

- 暂无跨设备同步、自定义主题编辑或自动分类；当前方案只预留扩展，数据库不是多设备同步协议。
- 下载任务可暂停、继续、编辑任务名称、删除记录和打开本地文件；删除时可选择永久删除下载目录中该视频的常见媒体文件和未完成文件，默认保留文件。文件删除只识别指定扩展名，未识别的文件会保留。应用关闭会中断任务，重新继续依赖 yt-dlp 对现有部分文件的恢复能力；已用本地 HTTP 和真实 yt-dlp 验证续传，来源网站及网络故障可能表现不同。
- 下载完成后先检查音视频流；中断后恢复、明显网络重试或下载速度重置等可观察风险会触发更耗时的完整解码检查。速度重置只是保守信号，可能多做检查，也无法识别所有静默断线；两种检查都不能保证发现所有损坏。检查失败的文件会保留，重新下载使用新文件。若无法确认后台进程停止，任务会提示检查进程，不能直接继续或删除文件；数据库持续无法写入且应用退出时，状态也可能无法持久保存。
- 下载文件名使用来源标题；标题变化时，原有未完成文件可能无法自动续传，会重新下载。
- 下载单个视频可选择自动格式或在高级格式中选择视频与音频组合。格式、大小和封面由来源实际提供。
- B 站支持粘贴 `bilibili.com/video/BV...` 链接，带 `p` 的分 P 分别入库；可在授权后读取 Chrome 的登录状态，浏览关注和自建收藏夹。失效视频会显示状态；短链接尚未接入。受限内容可按设置授权读取 Chrome Cookie，效果取决于账号权限和来源。
- 在线播放使用 yt-dlp 获取临时播放地址；YouTube 优先选择同时包含画面和声音的单一流，B 站支持分离音画流。播放能力取决于来源、登录状态和网络，开始播放不会创建下载任务。
- 播放器依赖本机 libVLC、X11/XWayland 和可用音频设备。截图及 Xvfb 测试不代表真实桌面画面、声音或硬件加速已验收。
- 本项目读取 YouTube 数据及下载的组合存在平台政策限制，具体参见开发者政策；本开发版没有完成相关合规审核。
- 用户已在真实 Ubuntu 桌面安装过旧版；`0.1.0` 的真实桌面安装、卸载及音视频效果仍需实际试用。CI 在隔离的 Ubuntu 24.04 环境检查安装、启动和卸载，不能替代真实桌面验证。
