# CampusTerminal 1.4.2

平台：Windows 10/11 x64。

本版合入 PR #2 的重连、更新入口、托盘与设置页改进，并修复不同用户的官方 iNode 安装目录或程序版本不同时无法接管的问题。

## 更新

- 根据 Windows 注册的官方 iNode 服务识别实际安装目录；接管时记录当前程序指纹，在服务停启前后及恢复预检查时复核，不再绑定开发机的单一文件哈希。校验只读取本地文件，不依赖联网证书检查。
- 设置页新增「检查更新」「更新日志」两张卡片；「每次启动自动检查更新」「发现新版本后自动更新并重启」拆分为两个默认关闭的开关，忽略的版本随设置保存。
- 更新日志按正式版标签读取：优先下载并校验 Release 的 `README.md` 资产（SHA-256 与大小），校验失败时回退到 Release 正文；没有说明时显示统一占位文案。长内容可滚动，卡片背景透明。
- 十分钟静默重试现在可以恢复本软件自己维持的会话：连通性验证在线时由后台记录恢复资格，认证失败和慢速重试期间保留；只有同一网卡、自动连接与自动重连开启、没有手机共享等替代网络时才允许接管 iNode。手动断开、关闭自动重连、切换网卡或把连接交还官方客户端后不再抢占。
- 设置页小窗口可读性：自动操作正文最小 14 px、标题最小 15 px，长标签自动换行，行高按字体度量计算；更新/日志按钮最小 13 px，卡片高度随字体调整；内容超出窗口时可纵向滚动。
- 勾选框改为矢量绘制（边框与对勾），按设备像素比渲染并在跨屏后重绘；点击区域扩展到整行，视觉图标保持紧凑。

- 托盘图标缓存 idle/wait/ok/err 四个 QIcon，状态未变化时不再重复 `setIcon`；闪烁复用缓存，Explorer 重建托盘时强制刷新一次。
- GUI 每分钟记录一次资源采样：GDI 对象数、USER 对象数、私有内存、窗口是否可见、托盘是否闪烁；窗口从隐藏恢复时补一条，用于定位 `CreateDIBSection failed` 的资源走势。
- 慢速重试每次记录恢复决策（是否持有恢复资格、网卡是否一致、自动连接/自动重连、替代网络、失败数和阻断原因）；核心记录接管接受、拒绝或取消的具体原因，便于日志定位。
- 感谢 [@LLLfish](https://github.com/LLLfish) 通过 [PR #2](https://github.com/HakureiTree/CampusTerminal-for-JNU-Zhuhai-/pull/2) 贡献更新与日志入口、慢速重连恢复、网卡身份与失败计数修复，以及托盘和设置页改进。

## 修复

- 修复安装版和便携版因官方 iNode 路径、程序文件版本或启动命令格式不同而出现 `Original service binary or command changed.` 的问题，兼容命令大小写、引号和空白差异。
- 官方客户端进程识别、恢复启动及认证日志读取统一使用服务对应的安装目录；缺少或无法读取启动快捷方式时直接启动已核验的程序。界面也按服务注册信息判断安装状态。
- 对服务缺失、程序缺失或不可读、路径歧义、服务身份变化和停启失败提供明确中文提示；保留正常服务停启、运行依赖检查及认证互斥逻辑。
- 慢速恢复接管在预检查后再次确认恢复资格、网卡和替代网络，避免检查期间用户设置变化后仍继续接管。
- 更新检查通过 Qt 信号回到主线程更新控件，重复检查请求不再并发；网络检查失败时显示重试提示并恢复原自动连接安排。
- 更新说明解析支持连续的“更新”“优化”“修复”段落，避免修复说明被截断；本版发行说明按 1.4.1 客户端可完整读取的顺序组织。
- 修复认证失败达到 5 次上限后，学校恢复认证但十分钟静默重试无法接管驻留 iNode、长期无法重新上线的问题。成功后失败计数清零。
- 修复 GUI 与后台对同一网卡 GUID 的大小写（以及有无大括号）判断不一致，导致静默重试始终没有发出恢复接管请求的问题。GUI 现在统一按 UUID 值比较，旧设置中已保存的大写网卡 ID 可直接继续使用。
- 修复慢速重试在认证开始前被 `OriginalClientRunning` 拒绝时，GUI 反复累计后台保留的旧认证错误（失败数从 5 涨到 45）的问题。现在以后台 `autoFailures` 为准；只有被接受的认证尝试才开启新的失败记账，认证前拒绝只记录并保留退避。
- 修复设置页在截图尺寸及最小窗口下文字过小、长标签被裁切、最后一行显示不全的问题；初始窗口也按实际字体高度排列更新卡片，避免卡片重叠。
- 修复更新日志卡片与设置页底色叠加的问题。

## 升级

升级前请先从托盘退出终端，再使用新版安装版或便携版。安装版按向导升级；便携版在原目录完整解压并覆盖程序文件，保留 `state/` 文件夹。

内置更新适用于 1.4.1 及之后的版本；1.4.1 客户端发现 v1.4.2 正式版后可直接通过内置更新升级。更新时会短暂断开校园网认证，完成后重新打开终端。

环境要求保持为 Windows 10/11 x64、Npcap 1.89 和 .NET 10 桌面运行库。启动器按需引导安装依赖，自动下载需要可用网络。

## 验证

- 整合后的公开源码 Python 回归 175 项：173 项通过，2 项为保留本机正在使用的后台而跳过。
- 后台检查 221 项、启动器检查 46 项通过，仅使用模拟认证帧与驱动平台。
- 服务发现、路径格式、不同文件版本、恢复身份复核、网卡 GUID、慢速接管、失败计数、托盘缓存、设置布局和更新流程回归通过。
- 便携版、266 文件完整更新清单与 1.4.1 增量包的文件大小、SHA-256 和隐私文件排除检查通过；增量包 18 个变更文件可重建一致的目标文件。
- 安装版和便携版的打包 GUI 预览、独立目录安装与卸载、安装登记清理通过。
- 小窗口初始布局及反复重排、100% / 125% / 150% 缩放截图检查通过。

本次验证不发起真实校园网认证，反馈用户环境、过夜重连与长期资源走势仍需实际环境确认。

## 下载

| 文件 | 用途 |
| --- | --- |
| [安装版](https://github.com/HakureiTree/CampusTerminal-for-JNU-Zhuhai-/releases/download/v1.4.2/CampusTerminal-1.4.2-windows-x64-setup.exe) | 按安装向导安装或升级 |
| [便携版](https://github.com/HakureiTree/CampusTerminal-for-JNU-Zhuhai-/releases/download/v1.4.2/CampusTerminal-1.4.2-windows-x64-portable.zip) | 完整解压后运行启动器 |
| [完整更新包](https://github.com/HakureiTree/CampusTerminal-for-JNU-Zhuhai-/releases/download/v1.4.2/CampusTerminal-1.4.2-windows-x64-payload.zip) | 供内置更新使用 |
| [1.4.1 增量包](https://github.com/HakureiTree/CampusTerminal-for-JNU-Zhuhai-/releases/download/v1.4.2/CampusTerminal-1.4.2-delta-from-1.4.1.zip) | 供 1.4.1 内置更新使用 |
| [更新清单](https://github.com/HakureiTree/CampusTerminal-for-JNU-Zhuhai-/releases/download/v1.4.2/update-manifest.json) | 版本与文件 SHA-256 清单 |
| [校验值](https://github.com/HakureiTree/CampusTerminal-for-JNU-Zhuhai-/releases/download/v1.4.2/SHA256SUMS.txt) | 发行文件的 SHA-256 |
| [源码清单](https://github.com/HakureiTree/CampusTerminal-for-JNU-Zhuhai-/releases/download/v1.4.2/SOURCE-SHA256SUMS.txt) | 对应公开源码及资源文件的 SHA-256 |
| [构建环境](https://github.com/HakureiTree/CampusTerminal-for-JNU-Zhuhai-/releases/download/v1.4.2/BUILD-ENVIRONMENT.txt) | 工具、依赖版本及构建提交 |

自主编译步骤见仓库根目录 [README](../../README.md#自主编译)。
