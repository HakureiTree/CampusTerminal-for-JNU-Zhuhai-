# CampusTerminal 1.4.2

平台：Windows 10/11 x64。

本版在 1.4.1 更新引擎的基础上补齐更新入口与更新日志，并修复断网恢复接管、托盘重复绘制和设置页小窗口可读性问题。

## 更新

- 设置页新增「检查更新」「更新日志」两张卡片；「每次启动自动检查更新」「发现新版本后自动更新并重启」拆分为两个默认关闭的开关，忽略的版本随设置保存。
- 更新日志按正式版标签读取：优先下载并校验 Release 的 `README.md` 资产（SHA-256 与大小），校验失败时回退到 Release 正文；没有说明时显示统一占位文案。长内容可滚动，卡片背景透明。
- 十分钟静默重试现在可以恢复本软件自己维持的会话：连通性验证在线时由后台记录恢复资格，认证失败和慢速重试期间保留；只有同一网卡、自动连接与自动重连开启、没有手机共享等替代网络时才允许接管 iNode。手动断开、关闭自动重连、切换网卡或把连接交还官方客户端后不再抢占。
- 设置页小窗口可读性：自动操作正文最小 14 px、标题最小 15 px，长标签自动换行，行高按字体度量计算；更新/日志按钮最小 13 px，卡片高度随字体调整；内容超出窗口时可纵向滚动。
- 勾选框改为矢量绘制（边框与对勾），按设备像素比渲染并在跨屏后重绘；点击区域扩展到整行，视觉图标保持紧凑。

## 优化

- 托盘图标缓存 idle/wait/ok/err 四个 QIcon，状态未变化时不再重复 `setIcon`；闪烁复用缓存，Explorer 重建托盘时强制刷新一次。
- GUI 每分钟记录一次资源采样：GDI 对象数、USER 对象数、私有内存、窗口是否可见、托盘是否闪烁；窗口从隐藏恢复时补一条，用于定位 `CreateDIBSection failed` 的资源走势。
- 慢速重试每次记录恢复决策（是否持有恢复资格、网卡是否一致、自动连接/自动重连、替代网络、失败数和阻断原因）；核心记录接管接受、拒绝或取消的具体原因，便于日志定位。

## 修复

- 修复认证失败达到 5 次上限后，学校恢复认证但十分钟静默重试无法接管驻留 iNode、长期无法重新上线的问题。成功后失败计数清零。
- 修复 GUI 与后台对同一网卡 GUID 的大小写（以及有无大括号）判断不一致，导致静默重试始终没有发出恢复接管请求的问题。GUI 现在统一按 UUID 值比较，旧设置中已保存的大写网卡 ID 可直接继续使用。
- 修复慢速重试在认证开始前被 `OriginalClientRunning` 拒绝时，GUI 反复累计后台保留的旧认证错误（失败数从 5 涨到 45）的问题。现在以后台 `autoFailures` 为准；只有被接受的认证尝试才开启新的失败记账，认证前拒绝只记录并保留退避。
- 修复设置页在截图尺寸及最小窗口下文字过小、长标签被裁切、最后一行显示不全的问题。
- 修复更新日志卡片与设置页底色叠加的问题。

## 升级

升级前请先从托盘退出终端，再使用新版安装版或便携版。安装版按向导升级；便携版在原目录完整解压并覆盖程序文件，保留 `state/` 文件夹。

内置更新适用于 1.4.1 及之后的版本；1.4.1 客户端发现 v1.4.2 正式版后可直接通过内置更新升级。更新时会短暂断开校园网认证，完成后重新打开终端。

环境要求保持为 Windows 10/11 x64、Npcap 1.89 和 .NET 10 桌面运行库。启动器按需引导安装依赖，自动下载需要可用网络。

## 验证

- 公开源码 Python 回归 164 项：162 项通过，2 项为保留本机现有后台而跳过。
- 后台检查 221 项、启动器检查 46 项通过；核心、GUI、启动器和更新包构建通过。
- 版本号 1.4.2，便携目录 269 个文件，更新清单 267 个文件；便携版、完整更新包、安装程序和更新清单均已生成。
- 针对恢复接管、托盘 10000 次相同状态仅 1 次图标更新、设置页最小字号/换行/滚动/整行点击等回归通过。
- 新增事故回放：GUI 大写 GUID 与核心小写 GUID 识别为同一网卡；iNode 驻留拒绝到恢复接管后最终 online 且失败计数清零；连续 30 次接管被拒不再累计失败数；手动断开、换网卡、关闭自动重连可抑制恢复请求。
- 打包后的 GUI `--preview --smoke` 退出码 0，日志中可见新增的 GUI 资源采样记录。

本次验证覆盖离线回归、源码构建和发行包验证。真实校园网过夜重连、整夜资源曲线与多 DPI 视觉检查仍需实际环境验证。

## 下载

| 文件 | 用途 |
| --- | --- |
| [安装版](https://github.com/HakureiTree/CampusTerminal-for-JNU-Zhuhai-/releases/download/v1.4.2/CampusTerminal-1.4.2-windows-x64-setup.exe) | 按安装向导安装或升级 |
| [便携版](https://github.com/HakureiTree/CampusTerminal-for-JNU-Zhuhai-/releases/download/v1.4.2/CampusTerminal-1.4.2-windows-x64-portable.zip) | 完整解压后运行启动器 |
| [完整更新包](https://github.com/HakureiTree/CampusTerminal-for-JNU-Zhuhai-/releases/download/v1.4.2/CampusTerminal-1.4.2-windows-x64-payload.zip) | 供内置更新使用 |
| [更新清单](https://github.com/HakureiTree/CampusTerminal-for-JNU-Zhuhai-/releases/download/v1.4.2/update-manifest.json) | 版本与文件 SHA-256 清单 |
| [校验值](https://github.com/HakureiTree/CampusTerminal-for-JNU-Zhuhai-/releases/download/v1.4.2/SHA256SUMS.txt) | 发行文件的 SHA-256 |
| [源码清单](https://github.com/HakureiTree/CampusTerminal-for-JNU-Zhuhai-/releases/download/v1.4.2/SOURCE-SHA256SUMS.txt) | 对应公开源码及资源文件的 SHA-256 |
| [构建环境](https://github.com/HakureiTree/CampusTerminal-for-JNU-Zhuhai-/releases/download/v1.4.2/BUILD-ENVIRONMENT.txt) | 工具、依赖版本及构建提交 |

自主编译步骤见仓库根目录 [README](../../README.md#自主编译)。
