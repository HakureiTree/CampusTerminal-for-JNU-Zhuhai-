# CampusTerminal 1.3.18

本仓库的首个发行版本。平台：Windows 10/11 x64。

在线发行页：[GitHub Release v1.3.18](https://github.com/HakureiTree/CampusTerminal-for-JNU-Zhuhai-/releases/tag/v1.3.18)。

| 发行物 | 使用方法 |
| --- | --- |
| [安装版](CampusTerminal-1.3.18-windows-x64-setup.exe) | 双击安装向导，选择目录和快捷方式；默认安装到 `%LOCALAPPDATA%\Programs\CampusTerminal` |
| [便携版](CampusTerminal-1.3.18-windows-x64-portable.zip) | 完整解压，运行 `CampusTerminal/开源暨珠有线网络终端.exe` |

便携版设置位于安装目录 `state/`；安装版设置位于 `%APPDATA%\CampusTerminal`。
安装版可以从 Windows 应用列表卸载，保留用户设置；升级或卸载前请先从托盘退出终端。

启动器自动检查 Npcap 驱动服务及 DLL，按需从 [官网](https://npcap.com/dist/npcap-1.89.exe) 下载 1.89，校验安装包后打开安装向导。安装选项已设为关闭 WinPcap 兼容模式。取消安装时，本次启动结束；要求重启时，重启电脑后再打开终端。已安装其它版本时，会提示版本差异。
需要 [.NET 10 桌面运行库 x64](https://aka.ms/dotnet/10.0/windowsdesktop-runtime-win-x64.exe)，启动器会按需从 Microsoft 下载。自动下载需要可用网络，离线电脑请提前准备 Npcap 和运行库。
普通认证直接运行发行包即可。原客户端交还中的 OCR 分支需要另行准备 Python 环境；学校官方客户端请通过学校提供的渠道获取。

本版支持普通认证、心跳、托盘、自动重连与可选的原客户端交还。发行包包含程序、资源、默认配置和许可文件。

验证结果：

- Python 离线测试 70 项，其中 68 项通过、2 项为保留本机现有认证会话而跳过。
- C# 核心检查 138 项、启动器离线检查 46 项通过。
- 官方安装器下载与缓存复用检查 2 项通过，数字签名有效；Npcap 驱动安装流程通过模拟平台验证。
- 便携包完整性、界面预览、安装版安装、运行期间卸载保护和卸载检查通过。

本次验证覆盖离线测试和安装流程。现场认证与长期稳定性还需结合实际校园网环境验证。

文件校验见 [SHA256SUMS.txt](SHA256SUMS.txt)，本版对应公开源码文件清单见 [SOURCE-SHA256SUMS.txt](SOURCE-SHA256SUMS.txt)。
源码校验清单对应 `v1.3.18` 标签。请在发行页下载该版本的源码归档进行验证；Windows 本地检出的换行设置可能影响校验。
公开依赖已在新建虚拟环境中实际安装、测试和打包；版本快照见 [BUILD-ENVIRONMENT.txt](BUILD-ENVIRONMENT.txt)。
从源码构建的完整步骤见 [自主编译](../../README.md#自主编译)。
