<div align="center">

<h1>开源暨珠有线网络终端</h1>

<p>暨南大学珠海校区宿舍有线的独立认证客户端<br>不是学校或 H3C 的官方客户端</p>

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
    <td align="center" width="33%"><b>只留在本机</b><br>密码不上传、不写进日志</td>
  </tr>
</table>

</div>

## 这是什么

宿舍有线要先通过 802.1X，电脑才拿得到地址。本终端做的就是这一步：选择网卡、登入、保持心跳，并显示这块网卡的流量。断线之后按固定规则重试。

它处理这一条有线认证，不代理上网，也不修改 DNS 或代理。其它网络可用时，会临时降低所选校园网卡的路由优先级，连接恢复后设回自动优先级；还会解除手机 USB 共享网卡上的 Npcap 绑定，避免干扰共享联网。

## 功能

- 普通 802.1X 认证（EAPOL / EAP-MD5）、周期心跳、正常注销
- 显示当前校园网卡的上传和下载速率
- 流量异常时，在限定次数内重新认证
- 开机自动启动；有线接入时自动尝试连接
- 自动重连连续失败 5 次后停止，并发出系统通知；之后每 10 分钟静默再试一次
- 其它网络正在占用时（例如 USB 共享）不自动重试，失败也不弹窗
- 还没连上校园网时，释放这块网卡的地址，避免挡住其它网络
- 关闭主窗口只收到托盘，认证继续。托盘菜单「退出程序」才会停止
- 勾选保存的学号和密码用当前 Windows 用户的 DPAPI 保护，只留在本机。运行日志不写密码

程序或计算机重新启动后，自动重连的失败次数清零。

## 明确不做

- 快速认证、单点登录。没有学校给出的协议约定，不能使用
- 特征伪造，以及靠它声称的无感重连、游戏保活
- 猜测学校何时停网，或在夜间主动断开

> [!NOTE]
> 跨天连续在线、自然断网后的恢复、开机后自己连上，这些路径已经接上，尚未做完长期现场验证。可以当日常客户端使用，不能把它看成已经证明不会掉线。

## 环境

- Windows 10 或 Windows 11，64 位
- 一块有线网卡
- 启动器自动检测 Npcap 驱动服务和 DLL；缺失时从 [Npcap 官方地址](https://npcap.com/dist/npcap-1.89.exe) 下载 **Npcap 1.89**，校验 SHA-256 后打开安装窗口。按向导完成安装即可，WinPcap 兼容模式已禁用
- 第一次配置需要管理员权限，用来安装驱动、补齐缺少的运行库，并登记以后不再反复弹出授权的后台任务
- 需要 [.NET 10 桌面运行库 x64](https://aka.ms/dotnet/10.0/windowsdesktop-runtime-win-x64.exe)。启动器在缺失时从 Microsoft 官方地址下载；尚不能上网的电脑请提前下载安装
- 公开发行包不捆绑 Npcap 或学校官方客户端安装包

网什么时候开、什么时候维护，由学校决定。

自动下载需要可用网络，可先连接手机共享；离线时请提前手动安装 Npcap 和运行库。Npcap 安装包缓存位于 `%LOCALAPPDATA%\CampusTerminal\installers`。安装完成后会再次检测，取消安装或要求重启时不会继续启动认证。核心固定校验 1.89 的 DLL 哈希；已安装其它版本时会提示版本不匹配，由你决定是否更换，启动器不会自动覆盖。

## 使用

完整发行说明和校验文件见 [GitHub Release v1.3.18](https://github.com/HakureiTree/CampusTerminal/releases/tag/v1.3.18)。

1. 下载 [1.3.18 安装版](https://github.com/HakureiTree/CampusTerminal/releases/download/v1.3.18/CampusTerminal-1.3.18-windows-x64-setup.exe) 或 [1.3.18 便携版](https://github.com/HakureiTree/CampusTerminal/releases/download/v1.3.18/CampusTerminal-1.3.18-windows-x64-portable.zip)。安装版按向导安装；便携版完整解压后运行「开源暨珠有线网络终端.exe」，不要从压缩包内直接运行或只拷贝一个程序。
2. 启动器检查本机环境；首次配置时同意管理员授权。如弹出 Npcap 安装窗口，按向导完成安装，随后自动继续配置并打开终端。
3. 填写学号和密码，选择有线网卡，用普通连接登入。
4. 点窗口关闭，程序缩到右下角托盘，认证不停。要停止时，在托盘菜单里选「退出程序」。

便携版的设置和凭据位于解压目录 `state/`；安装版位于 `%APPDATA%\CampusTerminal`，默认安装位置是 `%LOCALAPPDATA%\Programs\CampusTerminal`。安装版可从 Windows 应用列表卸载，卸载会保留用户设置和日志。升级或卸载前请先从托盘退出终端。

各版本按 `release/<版本号>/` 保存安装包、便携包、发行说明和 SHA-256 校验值，第一版为 **1.3.18**。

## 和学校官方客户端

官方客户端不是必需的，本终端可以单独认证。两者不能同时进行认证。

设置里有一项默认关闭的「学校官方客户端自动重连兜底」。打开后，只在本终端恢复失败，或你退出程序时，才结束自己的认证，再把连接交还官方客户端。手动断开不会交还。电脑上没有官方客户端时，这项保持关闭。交还时不会强行结束进程，也不修改服务的启动方式或网络配置。

本仓库不提供官方客户端安装包。需要应急使用时，请通过学校提供的渠道自行获取。

普通认证不需要 Python。原客户端交还中的 OCR 分支需要额外安装 Python 和 `requirements-ocr.txt` 中的依赖；可用 `CAMPUS_TERMINAL_OCR_PYTHON` 指定解释器，默认使用 PATH 中的 `python.exe`。该分支没有捆绑在发行包中，使用兜底前请先确认环境。

## 自主编译

以下命令均在本仓库根目录执行，使用 Windows x64 和 PowerShell。编译不需要学号、密码、官方客户端或本机抓包。

### 准备环境

- Python **3.13 x64**（此版本使用 3.13.5）
- [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)；启动器的目标框架是 .NET Framework 4.7.2，构建时 NuGet 会还原对应引用程序集
- [Inno Setup 6.7.3](https://jrsoftware.org/isdl.php) 或兼容的 Inno Setup 6，用于生成安装包；只编译便携版可以不安装

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

无需激活虚拟环境。编译核心及预览 GUI：

```powershell
dotnet build .\CampusTerminal\core\CampusTerminal.Core.csproj -c Release --configfile .\CampusTerminal\core\NuGet.Config
.\.venv\Scripts\python.exe .\CampusTerminal\run.py --preview
```

`--preview` 只预览界面，不读取保存的密码、不启动认证、不登记自启动。实际运行时去掉该参数，并先安装 Npcap 1.89 和 .NET 10 桌面运行库。

### 运行离线测试

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python.exe -m unittest discover -s .\CampusTerminal\tests -p 'test_*.py'
dotnet run --project .\CampusTerminal\tests\core\CoreTests.csproj -c Release
dotnet run --project .\CampusTerminal\tests\launcher\LauncherTests.csproj -c Release
Remove-Item Env:\QT_QPA_PLATFORM
```

Python 测试包含 GUI、凭据存储、通知、自启动、路径与模拟交还流程；C# 核心测试使用模拟认证帧，不会发送真实认证数据。启动器测试模拟 Npcap 缺失、安装成功、取消、重启和下载失败等路径，不安装驱动。本机已有认证后台运行时，会跳过涉及拉起测试后台的用例，以保留现有会话。私人抓包验密、现场验收记录和依赖本机配置的试用脚本未纳入此仓库。

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

`-OutputRoot` 可以指向仓库外的专用构建目录。生成包只收录程序、默认配置、必要脚本、资源和许可文件，不复制当前用户的设置、日志、抓包或第三方安装器。构建脚本不会进行真实认证或修改本机自启动项。

### 源码布局

| 路径 | 内容 |
| --- | --- |
| `CampusTerminal/gui/` | PyQt5 界面、图片与字体 |
| `CampusTerminal/core/` | .NET 认证、会话、联网核验和交还逻辑 |
| `CampusTerminal/packaging/` | PyInstaller、启动器、Inno Setup 和卸载脚本 |
| `CampusTerminal/operations/` | 后台任务与开发环境自启动登记 |
| `CampusTerminal/tests/` | 离线测试及模拟平台 |
| `src/`、`replacement/`、根目录 PowerShell 脚本 | 原客户端交还所需的支持代码，不包含本机 `config.json` |
| `CampusTerminal/core/vendor/inode-njit/` | 固定版本的协议上游源码及许可 |
| `release/` | 按版本归档的发行包 |

第三方版本、许可和对应源码位置见 [THIRD-PARTY.md](THIRD-PARTY.md)。字体及上游协议源码的许可证随源码保留。

## 隐私与安全

账号、密码和界面设置只写在本机，不上传。

> [!WARNING]
> 认证方式是 EAP-MD5。这是旧式方法，不能校验服务器证书。请只在自己的电脑上，对自己信任的构建输入校园网密码。

## 许可

认证协议实现改编自 [Besfim/inode-njit](https://github.com/Besfim/inode-njit)。本程序以 GPL-3.0-or-later 发布。再分发时必须保留许可证，并提供对应源码。

本程序与暨南大学、H3C 无关。开源软件仅供学习研究使用，作者不承担由使用本软件带来的任何法律责任。
