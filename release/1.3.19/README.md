# CampusTerminal 1.3.19

平台：Windows 10/11 x64。更新来自 [合并分支 #1](https://github.com/HakureiTree/CampusTerminal-for-JNU-Zhuhai-/pull/1)。

## 更新

- 主窗口和设置窗口支持拖动边框、四角缩放，保留输入内容和勾选状态。
- 设置页显示所选网卡的 IPv4 地址，支持复制，启动、切换网卡及连接或重连成功后刷新。
- GUI 和后台日志保留最近 31 个 UTC 日历日，补充调用超时、线程停滞及恢复记录，通过请求编号关联诊断信息，敏感字段经过过滤。
- 重连历史扩充至 100 条，按恢复过程去重；主界面显示最近 3 条。历史文件采用原子替换，损坏文件先备份再写入。

## 下载

| 发行物 | 使用方法 |
| --- | --- |
| [安装版](CampusTerminal-1.3.19-windows-x64-setup.exe) | 按向导安装，默认目录为 `%LOCALAPPDATA%\Programs\CampusTerminal` |
| [便携版](CampusTerminal-1.3.19-windows-x64-portable.zip) | 完整解压，运行 `CampusTerminal/开源暨珠有线网络终端.exe` |

升级前请先从托盘退出终端。启动器按需引导安装 Npcap 1.89 和 .NET 10 桌面运行库，自动下载需要可用网络。便携版设置位于 `state/`，安装版设置位于 `%APPDATA%\CampusTerminal`。

## 验证

- Python 回归 100 项：98 项通过，2 项为保留本机现有后台而跳过。
- 后台检查 172 项、启动器检查 46 项通过。
- 便携包完整性、缩放界面预览、安装版安装与卸载检查通过。

本次验证覆盖离线回归和安装流程；校园网现场认证与长期稳定性仍需实际环境验证。

文件校验见 [SHA256SUMS.txt](SHA256SUMS.txt)，源码校验见 [SOURCE-SHA256SUMS.txt](SOURCE-SHA256SUMS.txt)，构建环境见 [BUILD-ENVIRONMENT.txt](BUILD-ENVIRONMENT.txt)。源码清单对应 `v1.3.19` 的 GitHub 源码归档；本地检出的换行设置可能影响校验。编译步骤见 [自主编译](../../README.md#自主编译)。
