---
name: MediaDesk
description: "Linux 桌面个人音视频工作台的当前试行视觉实现。"
colors:
  dark-canvas: "#171a1b"
  dark-surface: "#252a2a"
  dark-ink: "#f2f5f4"
  dark-rail: "#232933"
  dark-banner: "#163677"
  dark-selected: "#f1d867"
  dark-rule: "#eecf60"
  light-canvas: "#f4f3ee"
  light-surface: "#fffef9"
  light-ink: "#192c30"
  light-rail: "#e9e3d8"
  light-banner: "#24498d"
  light-selected: "#24498d"
  light-action: "#24498d"
  nabis-canvas: "#1d1c23"
  nabis-surface: "#2b2932"
  nabis-ink: "#f8f0e8"
  nabis-rail: "#342c3b"
  nabis-banner: "#863f52"
  nabis-selected: "#efc486"
  neo-canvas: "#f8f3e8"
  neo-surface: "#fffef7"
  neo-ink: "#243a44"
  neo-rail: "#cadfd7"
  neo-rail-muted: "#4d6269"
  neo-banner: "#205f69"
  neo-selected: "#a34735"
  neo-action: "#205f69"
typography:
  display:
    fontFamily: "Noto Serif CJK SC, serif"
    fontSize: "27px"
    fontWeight: 700
  headline:
    fontFamily: "Noto Serif CJK SC, serif"
    fontSize: "30px"
    fontWeight: 700
  title:
    fontFamily: "Sans"
    fontSize: "15px"
    fontWeight: 700
  section:
    fontFamily: "Sans"
    fontSize: "18px"
    fontWeight: 700
  label:
    fontFamily: "Sans"
    fontSize: "12px"
    fontWeight: 700
rounded:
  button: "4px"
  card: "4px"
  cover: "0px"
  editorial-item: "0px"
spacing:
  content: "25px"
  row-gap: "12px"
  media-inner: "6px"
  media-gap: "7px"
  card: "20px"
---

# Design System: MediaDesk

## Overview

用户选择的方向是**唱片封套＋编辑设计**：封面、衬线标题、色块页眉和分隔线构成内容索引。当前 GTK 3 实现是试行表达；复审认可其视觉识别度，同时认为表达偏克制；用户尚未进行最终视觉认可。MediaDesk 是工作名。

当前视觉重点集中在媒体库、侧栏、设置与下载页页眉和主要操作；不能把这些局部样式视作全产品已完成的设计系统。产品要求先锋、大胆、有辨识度，同时支持日常阅读和操作；内容封面保留原始内容与比例。

## Colors

四套外观在设置中切换，前置 tokens 记录各套主要实际色值；完整状态色及覆盖顺序以 `mediadesk/app.py` 的 CSS 为准。

- **深色**：深石墨内容区与收敛的深色导航栏、蓝色页眉、暖黄色选中项及主要操作；黄色分隔线强调媒体索引。
- **浅色**：暖白内容区与浅色导航栏、蓝色页眉和导航选中项；主要操作为蓝底浅字。
- **纳比派**：中性深墨内容区与紫棕导航栏形成明暗层次；酒红页眉与杏色选中项、主要操作构成暖色节奏。
- **新印象主义**：暖纸色内容区与冷绿导航栏对照，青蓝页眉和主要操作配合少量陶红选中项与索引线。

选中项同时有文字、图标与底色；状态不能只依赖颜色。媒体封面本身提供内容色彩，不重新着色。

## Typography

正文和媒体项标题优先使用 `Noto Sans CJK SC`，缺失时回退 GTK `Sans`；展示标题优先使用 `Noto Serif CJK SC`，缺失时回退系统 `serif`，不依赖在线字体。媒体库标题为 27px、700，其他页面标题 30px、700；区段标题 18px、粗体，媒体项标题 15px、700；导航分组标题 12px、粗体。两种 Noto 字体均取决于本机安装情况；系统回退后的跨机器视觉一致性尚未验证。

## Layout

桌面主工作区左侧导航请求宽度 210px，主区边距 25px。媒体库使用 FlowBox，常见桌面宽度最多四列；超宽窗口按可用宽度逐步增加列数，间距 12px；每个条目为封面在上、元数据在下的纵向布局，条目请求最小宽度 210px，封面最小宽度 190px。标题最多两行并省略，完整标题可通过提示查看；频道、来源与本地状态在封面下显示。媒体库还提供紧凑列表及详细视图，条目之间使用细分隔线，详细视图展示标题、来源／频道、时长和状态，显示方式通过并排图标直接切换，选中状态清晰，图标提供提示与可访问名称；选择保存在本地，搜索和详情返回时保持当前视图。空状态左对齐，顶部留白 48px。

封面容器按 16:9 计算，图片按原比例适配、不裁剪，有图时采用深色留边；缺图时显示中性图标。详情区在可用宽度小于 680px 时由左右排列切换为上下排列，播放器及操作区仍需结合真实窗口和内容验证。移动端不属于当前产品承诺。

## Elevation & Depth

主要依靠平面色块、线条和明度区分层次；按钮按下时使用内阴影，常态不依赖大面积投影。按钮颜色、边界和阴影变化为 120ms；尊重 reduced motion 是产品要求，当前代码是否完整实现尚待验证。

## Shapes

普通按钮为 6px 圆角，普通容器 8px；媒体封面底板通常为 4px，媒体库条目和导航按钮为直角。纳比派外观对普通容器及封面另有更方的覆盖。具体样式受后续 CSS 覆盖影响，以代码最终生效值为准。

## Components

- **导航**：收敛的主题侧栏按媒体库、列表、发现、平台等分组；当前项以色块及文字、图标颜色变化区分。平台显示简短连接状态，完整状态通过提示和设置页查看。焦点使用 2px 轮廓。
- **页眉**：媒体库、设置和下载页使用主题色块页眉。
- **媒体库条目**：上方 16:9 封面，下方先是 3px 色线，再列标题、可选频道、来源与本地状态；整体为可操作按钮，hover 和 focus 有反馈。
- **按钮与输入**：主要操作使用对应外观强调色；普通按钮有边框、hover 和按下状态，按钮焦点有 2px 轮廓。输入控件使用主题表面色；完整键盘可访问性与焦点表现仍需实测。
- **详情和下载**：详情包含播放器、来源信息与操作；下载任务显示文字状态、可用进度及操作。状态、失败原因和文件可用性不能只通过颜色传达。

## Do's and Don'ts

- **Do** 保留封面原始比例，缺失时使用中性占位。
- **Do** 让图标按钮有可访问名称，状态有文字说明，并保持键盘焦点可见；这些是要求，不表示全部路径已通过验证。
- **Do** 在账号连接、联网读取和本地扫描前遵循 `docs/product-principles.md` 的告知与选择原则；视觉测试使用隔离示例，不读取真实账号、Cookie 或用户媒体。
- **Don't** 把示例内容呈现为真实数据，或把未下载、失效、缺失的文件显示为可用。
- **Don't** 把当前试行样式或静态检查描述成用户视觉验收。

参考来源：`PRODUCT.md`、`docs/product-principles.md`、`mediadesk/app.py`；旧版提案曾参考 `awesome-design-md/design-md/spotify/DESIGN.md` 与 `awesome-design-md/design-md/linear.app/DESIGN.md` 的媒体内容优先、层级和紧凑控件。当前实现及用户选择的方向是本记录的直接依据；旧参考不代表对其品牌视觉的复刻。
