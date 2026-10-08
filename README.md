<div align="center">

<h1>开源暨珠有线网络终端</h1>

<p>面向暨南大学珠海校区宿舍有线网络<br>独立开发的开源 802.1X 认证客户端</p>

<p>
  <a href="https://www.gnu.org/licenses/gpl-3.0"><img alt="许可证：GPL-3.0" src="https://img.shields.io/badge/%E8%AE%B8%E5%8F%AF%E8%AF%81-GPL--3.0-2563EB?style=flat&logo=gnu&logoColor=white" /></a>
  <img alt="平台：Windows 10 / 11" src="https://img.shields.io/badge/%E5%B9%B3%E5%8F%B0-Windows%2010%20%2F%2011-0078D4?style=flat&logo=windows&logoColor=white" />
  <img alt="版本：1.3.18" src="https://img.shields.io/badge/%E7%89%88%E6%9C%AC-1.3.18-3F6212?style=flat" />
</p>

<p>
  <a href="#功能"><b>功能</b></a>
  &nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="#环境"><b>环境</b></a>
  &nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="#使用"><b>使用</b></a>
  &nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="#自主编译"><b>自主编译</b></a>
  &nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="#许可"><b>许可</b></a>
</p>

<table>
  <tr>
    <td align="center" width="33%"><b>普通 802.1X</b><br>选择网卡后登入</td>
    <td align="center" width="33%"><b>保持会话</b><br>心跳，断线按规则重试</td>
    <td align="center" width="33%"><b>本机保存</b><br>Windows DPAPI 加密凭据</td>
  </tr>
</table>

</div>

## 简介

宿舍有线网络通过 802.1X 认证后获得网络地址。在终端中选择网卡、填写学号和密码，即可连接校园网。连接后持续发送心跳，显示网卡流量，并在断线后按规则重试。

使用手机 USB 共享等其它网络时，终端会临时降低校园网卡的路由优先级，校园连接恢复后设回自动优先级。手机共享网卡上的 Npcap 绑定也会解除，让共享联网正常工作。

## 功能

- 普通 802.1X 认证（EAPOL / EAP-MD5）、周期心跳、正常注销
- 显示当前校园网卡的上传和下载速率
- 主窗口和设置窗口支持拖动边框及四角调整大小，界面按比例缩放
- 设置中显示所选网卡的当前 IPv4 地址，每次连接或重连成功后刷新，可选中复制
- 流量异常时，在限定次数内重新认证
- 开机自动启动；有线接入时自动尝试连接
- 自动重连连续失败 5 次后停止，并发出系统通知；之后每 10 分钟静默再试一次
- 其它网络正在使用时（例如 USB 共享），自动重连进入等待状态
- 校园认证前释放所选网卡的地址，让其它网络正常工作
- 关闭主窗口只收到托盘，认证继续。托盘菜单「退出程序」才会停止
- 按需保存学号和密码，通过当前 Windows 用户的 DPAPI 加密保护

程序或计算机重新启动后，自动重连的失败次数清零。

> [!NOTE]
> 跨天在线、自然断网恢复和开机自动连接的长期稳定性，还需结合实际校园网环境验证。当前测试范围见 [发行说明](release/1.3.18/README.md)。

## 环境

- Windows 10 或 Windows 11，64 位
- 一块有线网卡
- **Npcap 1.89**：启动器检查驱动服务和 DLL，按需从 [Npcap 官网](https://npcap.com/dist/npcap-1.89.exe) 下载，校验 SHA-256 后打开安装向导。安装选项已设为关闭 WinPcap 兼容模式
- [.NET 10 桌面运行库 x64](https://aka.ms/dotnet/10.0/windowsdesktop-runtime-win-x64.exe)：启动器按需从 Microsoft 官方地址下载并安装
- 首次配置需要管理员授权，用于安装驱动、运行库和登记认证后台任务

自动下载需要可用网络，可以先接入手机共享。离线电脑请提前准备 Npcap 和运行库。Npcap 安装包缓存位于 `%LOCALAPPDATA%\CampusTerminal\installers`。

安装完成后，启动器会再次检查环境，再打开终端。取消安装时，本次启动结束；安装器要求重启时，重启电脑后再打开终端。本版支持 Npcap 1.89，并校验其 DLL 哈希；已安装其它版本时，会提示版本差异，由你决定是否更换。

## 使用

完整发行说明和校验文件见 [GitHub Release v1.3.18](https://github.com/HakureiTree/CampusTerminal-for-JNU-Zhuhai-/releases/tag/v1.3.18)。

1. 下载 [1.3.18 安装版](https://github.com/HakureiTree/CampusTerminal-for-JNU-Zhuhai-/releases/download/v1.3.18/CampusTerminal-1.3.18-windows-x64-setup.exe) 或 [1.3.18 便携版](https://github.com/HakureiTree/CampusTerminal-for-JNU-Zhuhai-/releases/download/v1.3.18/CampusTerminal-1.3.18-windows-x64-portable.zip)。安装版按向导安装；便携版完整解压后，在解压目录运行「开源暨珠有线网络终端.exe」。
2. 启动器检查本机环境；首次配置时同意管理员授权。如弹出 Npcap 安装窗口，按向导完成安装，随后自动继续配置并打开终端。
3. 填写学号和密码，选择有线网卡，用普通连接登入。
4. 点窗口关闭，程序缩到右下角托盘，继续保持认证。要停止时，在托盘菜单里选「退出程序」。

便携版的设置和凭据位于解压目录 `state/`；安装版位于 `%APPDATA%\CampusTerminal`，默认安装位置是 `%LOCALAPPDATA%\Programs\CampusTerminal`。安装版可从 Windows 应用列表卸载，卸载会保留用户设置和日志。升级或卸载前请先从托盘退出终端。

各版本按 `release/<版本号>/` 保存安装包、便携包、发行说明和 SHA-256 校验值，第一版为 **1.3.18**。

### 日志

GUI 事件写入用户设置目录中的 `gui-events.jsonl`（便携版为 `state/`，安装版为 `%APPDATA%\CampusTerminal`），记录自动连接、跳过原因、后台错误和网卡路径变化。`backend-probe.json` 保存后台可执行文件的定位信息。

认证后台的日志固定写入 `%APPDATA%\CampusTerminal\logs\events-YYYYMMDD.jsonl`，记录认证、DHCP 地址更新、断线恢复及交还官方客户端等阶段；`heartbeat.json` 每 5 秒更新运行状态。后台日志按日期保存，单文件超过 8 MiB 后滚动，并在后台启动时清理较旧文件。GUI 事件日志目前没有轮转。

`%APPDATA%\CampusTerminal\recovery-events.json` 保存最近三次重连记录。官方客户端交还过程的诊断文件另存于程序数据根目录的 `logs/campus-terminal/<运行编号>/`。

## 配合学校官方客户端

本终端可以独立完成认证。两个客户端轮流使用：启动本终端前，先断开官方客户端的连接。

设置中的「学校官方客户端自动重连兜底」默认关闭。启用后，在本终端恢复失败或退出程序时，将连接交还官方客户端。手动断开时保持断开状态。交还过程沿用官方客户端现有的进程、服务和网络配置。

启用这项功能前，请通过学校提供的渠道获取官方客户端，并完成安装和配置。

普通认证直接运行发行包即可。原客户端交还中的 OCR 分支需要另行安装 Python 和 `requirements-ocr.txt` 中的依赖；可用 `CAMPUS_TERMINAL_OCR_PYTHON` 指定解释器，默认使用 PATH 中的 `python.exe`。

## 自主编译

以下命令均在本仓库根目录执行，使用 Windows x64 和 PowerShell。编译所需的源码、资源和依赖清单均已收录在仓库中。

### 准备环境

- Python **3.13 x64**（此版本使用 3.13.5）
- [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)；启动器的目标框架是 .NET Framework 4.7.2，构建时 NuGet 会还原对应引用程序集
- [Inno Setup 6.7.3](https://jrsoftware.org/isdl.php) 或兼容的 Inno Setup 6，用于生成安装版

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

以下命令直接调用虚拟环境中的解释器。编译核心及预览 GUI：

```powershell
dotnet build .\CampusTerminal\core\CampusTerminal.Core.csproj -c Release --configfile .\CampusTerminal\core\NuGet.Config
.\.venv\Scripts\python.exe .\CampusTerminal\run.py --preview
```

`--preview` 用于界面预览。正式认证时去掉该参数，并先安装 Npcap 1.89 和 .NET 10 桌面运行库。

### 运行离线测试

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python.exe -m unittest discover -s .\CampusTerminal\tests -p 'test_*.py'
dotnet run --project .\CampusTerminal\tests\core\CoreTests.csproj -c Release
dotnet run --project .\CampusTerminal\tests\launcher\LauncherTests.csproj -c Release
Remove-Item Env:\QT_QPA_PLATFORM
```

Python 测试覆盖 GUI、凭据存储、通知、自启动、路径与模拟交还流程。C# 核心测试使用模拟认证帧；启动器测试通过模拟平台覆盖 Npcap 检测、安装成功、取消、重启和下载失败等情况。本机已有认证后台运行时，会跳过需要拉起测试后台的用例，保留当前会话。

### 生成便携版和安装版

```powershell
.\CampusTerminal\packaging\Publish.ps1 -Python .\.venv\Scripts\python.exe -OutputRoot .\build
.\CampusTerminal\packaging\Build-Installer.ps1 -SourceDir .\build\CampusTerminal -OutputDir .\build -Iscc 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
```

若 Inno Setup 安装在其它位置，将 `-Iscc` 改为实际路径；已加入 PATH 时可省略此参数。输出：

```text
build/
├─ CampusTerminal/                              # 可运行的完整便携目录
├─ CampusTerminal-1.3.18-windows-x64-portable.zip
└─ CampusTerminal-1.3.18-windows-x64-setup.exe
```

输出包含程序、默认配置、支持脚本、资源和许可文件。`-OutputRoot` 可以指向仓库外的专用构建目录。打包完成后，运行生成的启动器进行首次环境配置。

### 源码布局

| 路径 | 内容 |
| --- | --- |
| `CampusTerminal/gui/` | PyQt5 界面、图片与字体 |
| `CampusTerminal/core/` | .NET 认证、会话、联网核验和交还逻辑 |
| `CampusTerminal/packaging/` | PyInstaller、启动器、Inno Setup 和卸载脚本 |
| `CampusTerminal/operations/` | 后台任务与开发环境自启动登记 |
| `CampusTerminal/tests/` | 离线测试及模拟平台 |
| `src/`、`replacement/`、根目录 PowerShell 脚本 | 原客户端交还所需的 PowerShell 和 OCR 支持代码 |
| `CampusTerminal/core/vendor/inode-njit/` | 固定版本的协议上游源码及许可 |
| `release/` | 按版本归档的发行包 |

第三方版本、许可和对应源码位置见 [THIRD-PARTY.md](THIRD-PARTY.md)。字体及上游协议源码的许可证随源码保留。

## 隐私与安全

账号、密码和界面设置保存在本机。密码通过当前 Windows 用户的 DPAPI 加密保护，运行日志记录连接状态和错误信息。

> [!WARNING]
> EAP-MD5 不提供服务器证书验证。请在自己的电脑上使用可信构建，并确认连接的是学校网络。

## 许可

认证协议实现改编自 [Besfim/inode-njit](https://github.com/Besfim/inode-njit)。本程序以 GPL-3.0-or-later 发布。再分发时必须保留许可证，并提供对应源码。
