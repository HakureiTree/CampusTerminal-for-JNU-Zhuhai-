# CampusTerminal 1.3.18

本仓库的首个发行版本。平台：Windows 10/11 x64。

在线发行页：[GitHub Release v1.3.18](https://github.com/HakureiTree/CampusTerminal/releases/tag/v1.3.18)。

| 发行物 | 使用方法 |
| --- | --- |
| [安装版](CampusTerminal-1.3.18-windows-x64-setup.exe) | 双击安装向导，选择目录和快捷方式；默认安装到 `%LOCALAPPDATA%\Programs\CampusTerminal` |
| [便携版](CampusTerminal-1.3.18-windows-x64-portable.zip) | 完整解压，运行 `CampusTerminal/开源暨珠有线网络终端.exe` |

便携版设置位于安装目录 `state/`；安装版设置位于 `%APPDATA%\CampusTerminal`。
安装版可以从 Windows 应用列表卸载，保留用户设置；升级或卸载前请先从托盘退出终端。

启动器自动检测 Npcap 驱动服务及 DLL，缺失时从 [官方地址](https://npcap.com/dist/npcap-1.89.exe) 下载 1.89，校验安装包后打开安装窗口；按向导完成安装即可，WinPcap 兼容模式已禁用。取消或需要重启时停止启动认证，已安装其它版本时提示版本不匹配。
需要 [.NET 10 桌面运行库 x64](https://aka.ms/dotnet/10.0/windowsdesktop-runtime-win-x64.exe)，缺失时启动器从 Microsoft 下载；尚未联网的电脑请提前安装。
公开包不捆绑 Npcap、官方 iNode 或 .NET 安装器。原客户端兜底中的 OCR 分支需要另行准备 Python 环境；普通认证不依赖外部 Python。

本版使用当前 1.3.18 源码构建，保留普通认证、心跳、托盘、自动重连与可选原客户端交还逻辑。
便携包按公开发行要求重新整理，去除私人状态、第三方安装器，并补齐许可文件。

验证结果：Python 离线测试 70 项（本机已有用户后台运行，2 项保护现有会话而跳过）；C# 核心检查 138 项通过；
新增启动器离线检查 46 项及官方下载、缓存复用检查 2 项通过，官方安装包数字签名有效；未在本机重新安装 Npcap 驱动。
便携包完整性及无认证预览通过；安装、安装版预览、运行期间卸载保护和卸载均通过。
未重新进行真实校园网络认证和长期现场验证。

文件校验见 [SHA256SUMS.txt](SHA256SUMS.txt)，本版对应公开源码文件清单见 [SOURCE-SHA256SUMS.txt](SOURCE-SHA256SUMS.txt)。
源码校验值按 GitHub 生成的源码归档内容计算；Windows 本地检出时换行符可能改变，验证源码请使用发行页下载的源码归档。
公开依赖已在新建虚拟环境中实际安装、测试和打包；版本快照见 [BUILD-ENVIRONMENT.txt](BUILD-ENVIRONMENT.txt)。
从源码构建的完整步骤见 [自主编译](../../README.md#自主编译)。
