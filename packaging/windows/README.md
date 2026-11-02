# Windows 预构建 payload 安装候选

当前交付为构建/安装脚本，尚无最终 Windows 发行包。默认归档安装检查归档与关键组件，不执行解压后全量逐文件 SHA；完整安装计时和真实桌面体验以主分支对应版本的验证记录为准。

终端用户使用完整发行包，双击 `packaging/windows/Install MediaDesk.cmd`。发行包必须包含 `mediadesk/`、必要安装脚本、`packaging/windows/mediadesk.ico` 与 `runtime-payload/`。推荐 payload 为 `runtime.zip`、`runtime-archive.json`、`runtime-files.json` 三文件；也支持完整展开目录。归档 SHA、所有条目路径/类型/长度、原生解压退出状态与解压后的路径类型均检查；关键组件须存在且长度匹配。默认不计算解压后所有文件的 SHA，不能保证检出全部解压后内容损坏。展开目录 payload 仍完整检查来源及复制结果的逐文件 SHA。源码 checkout 本身不是完整安装包；缺 payload 时会在写入前拒绝。用户不需要安装 MSYS2、Python、GTK、VLC、FFmpeg 或 Node；setup 不下载软件，不修改系统 PATH，无需管理员权限。

默认应用目录 `%LOCALAPPDATA%\Programs\MediaDesk`，私有依赖位于相邻 `MediaDesk-runtime`，快捷方式仅在当前用户开始菜单。安装先写入带 ownership 的 staging 目录，通过该 payload 形式对应的检查后原子提升；检查失败不提升为已安装 runtime。复用已有 runtime 时仍须完整逐文件 SHA 匹配，不能仅凭新归档的校验结果信任可变的旧目录。展开目录形式的 payload 可在中断后复用相同 payload 已复制的文件；归档形式重试时保留旧 staging，并创建新目录重新解压。未知或修改的 staging 文件会保留，日志给出位置。已有 app 目录拒绝覆盖；关闭→卸载应用文件→重新安装，用户数据保留。应用复制到独立 staging，复制失败不占用最终应用路径；进入最终路径前已有可卸载清单。

卸载默认同时移除本安装拥有、哈希仍匹配的私有运行时与程序文件；`uninstall.ps1 -KeepRuntime` 可保留依赖以供重装。未知、修改文件及 `%LOCALAPPDATA%\MediaDesk` 用户数据保留；不强杀运行中的应用。安装失败保留日志 `%TEMP%/MediaDesk-setup-*.log` 与现场，不报告成功。安装包更新、安装注册与最终 GUI 包装由主分支集成。

`prepare-runtime.ps1` / `prepare-vlc.ps1` 为先前隔离开发环境实验，不由用户 setup 调用，不得作为最终安装流程。构建环境不随应用分发；运行时构建工具仍在整理，尚未作为完整构建流程交付。

可用测试：`test-archive.ps1` 验证归档篡改、路径穿越和链接拒绝，以及原生解压/卸载；`test-payload.ps1` 验证损坏内容拒绝、staging 恢复与未知/修改文件保留；`test-install.ps1` 验证应用安装/卸载。干净 PATH 不等于真实桌面画面/声音已验证。

## 高级：外部运行时安装

以下 `install.ps1` 是源码安装/卸载路径，依赖预检成功后才复制程序。当前不自动下载运行时，不是可在干净 Windows 上直接双击安装的独立安装器。脚本没有管理员操作，不改系统 PATH，不安装/卸载外部运行时。

## 依赖

所有原生组件须与运行时架构一致，本轮只验证 Windows x64、MSYS2 UCRT64 Python 3.14/GTK3 和 VLC 3。

| 组件 | 提供方式 | 许可证与交付边界 |
| --- | --- | --- |
| Python、GTK3、PyGObject、Cairo、图标/typelib | 外部 MSYS2 UCRT64 安装 | Python PSF；GTK/PyGObject LGPL-2.1-or-later；其余依赖各有许可证。当前脚本不复制运行时 |
| requests、google-auth、google-auth-oauthlib、yt_dlp Python库 | 安装在同一 UCRT64 Python，或显式 `PythonPackages` 目录 | google-auth/oauthlib Apache-2.0；requests Apache-2.0；yt-dlp wheel Unlicense；传递依赖单独核对 |
| libVLC 与 plugins | 外部同架构 VLC 3 安装目录 | libVLC 核心 LGPL2.1；完整 VLC/插件另有许可证，不能把完整目录统称 LGPL |
| yt-dlp.exe | 外部可执行文件 | 上游说明 PyInstaller 合并发行物含 GPLv3+ 代码，不能仅按仓库的 Unlicense 处理 |
| ffmpeg.exe、ffprobe.exe | 外部二进制目录 | 按具体构建配置确定 LGPL/GPL，`full_build` 不能默认按 LGPL |
| Node 与 yt-dlp EJS | YouTube 提取相关依赖 | 上游要求完整 YouTube 支持需 EJS 和可用 JS runtime；预检只报告 Node 是否存在，不证明线上提取可用 |

在外部 MSYS2 UCRT64 环境中，可使用官方包（`pacman` 会解析传递依赖）：

```sh
pacman -S --needed mingw-w64-ucrt-x86_64-python \
  mingw-w64-ucrt-x86_64-gtk3 mingw-w64-ucrt-x86_64-python-gobject \
  mingw-w64-ucrt-x86_64-python-requests \
  mingw-w64-ucrt-x86_64-python-google-auth-oauthlib \
  mingw-w64-ucrt-x86_64-yt-dlp mingw-w64-ucrt-x86_64-yt-dlp-ejs
```

这里的命令是运行时准备说明，安装脚本不执行它；用户或主分支交付负责人管理运行时更新。VLC、FFmpeg、yt-dlp.exe 仍需可用。`PythonPackages` 仅适合经过核对的外部 Python 包目录，不会把 CPython Windows 二进制 wheel 转换成 MSYS2/Mingw ABI。

## 使用

在包含 `mediadesk/` 与本目录的源码树中，用 Windows PowerShell 执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\packaging\windows\install.ps1 `
  -RuntimeBin 'C:\msys64\ucrt64\bin' `
  -VlcDir 'C:\Program Files\VideoLAN\VLC' `
  -ToolDirectories 'C:\media-tools'
```

默认程序位置：`%LOCALAPPDATA%\Programs\MediaDesk`。默认快捷方式位于当前用户开始菜单的 `MediaDesk` 目录。两条快捷方式均引用安装目录内的 `mediadesk.ico`，沿用应用 SVG 的图形，包含 16–256 px 尺寸；图标文件纳入安装 manifest，卸载时按哈希清理。`-InstallRoot`、`-ShortcutRoot` 可用于隔离验证；`-NoShortcut` 跳过快捷方式。

安装先调用 `doctor.py`，检查依赖导入、GTK版本、VLC DLL加载、下载/解码工具版本。缺依赖则退出，安装目录尚未创建。预检不读取账号、Cookie、媒体库或用户媒体，也不验证画面、声音、网络、Google客户端配置或OAuth授权。`ready: true` 仅表示这些运行时检查通过。

安装后：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\Programs\MediaDesk\start.ps1" -CheckOnly
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\Programs\MediaDesk\uninstall.ps1"
```

卸载只删除 manifest 中哈希仍匹配的程序文件和本安装创建的快捷方式；修改过或未知文件保留。`%LOCALAPPDATA%\MediaDesk` 中的数据库、下载文件、Google配置和外部依赖不会删除。正在运行时拒绝卸载；不强杀程序。已有安装目录会拒绝覆盖，当前更新方式为关闭程序→卸载程序文件→重新安装，数据目录保留。安装中途遇到磁盘/权限错误会保留现场，不宣称安装成功。

## 本轮证据与限制

现有 MSYS2 原型只有 gi/cairo，缺请求、Google授权及 yt_dlp Python库。为验证脚本，在单独临时目录解包了纯 Python wheel overlay，没有修改该 MSYS2 或系统安装。此验证 overlay 解析得到 google-auth 2.47.0，并非最新 google-auth 的可发布依赖方案；新版依赖可能需要同 ABI 的 cryptography 等原生包。正式准备运行时优先使用上述 MSYS2 包，不复制该临时 overlay 作为产品运行时。

隔离测试覆盖：缺运行时/缺包拒绝且不写安装目录、成功安装和安装后预检、快捷方式、已有目录拒绝覆盖、卸载保留数据哨兵、保留修改/未知文件。未执行用户真实桌面快捷方式点击、物理声音、真实账户授权或系统“已安装应用”注册。本目录不包含最终安装包；主分支负责打包。

现有外部目录实测文件体积（未压缩，非最小依赖裁剪结果）：UCRT64 原型约 809 MB，VLC约192 MB，FFmpeg约227 MB，FFprobe约227 MB，yt-dlp.exe约18 MB；临时纯Python overlay约15 MB。整体复制这套实验依赖超过1.4 GB，不能据此宣称已得到精简可分发运行时。源码脚本仅数百 KB 级，实际产品体积以主分支构建结果为准。

来源：

- [MSYS2 PyGObject](https://packages.msys2.org/package/mingw-w64-ucrt-x86_64-python-gobject)、[GTK3](https://packages.msys2.org/package/mingw-w64-ucrt-x86_64-gtk3)、[Google OAuth](https://packages.msys2.org/package/mingw-w64-ucrt-x86_64-python-google-auth-oauthlib)、[yt-dlp](https://packages.msys2.org/package/mingw-w64-ucrt-x86_64-yt-dlp?repo=ucrt64)。
- [VideoLAN libVLC](https://www.videolan.org/vlc/libvlc.html)。
- [FFmpeg 许可证按构建变化](https://ffmpeg.org/legal.html)。
- [yt-dlp Licensing 与依赖](https://github.com/yt-dlp/yt-dlp#licensing)。
