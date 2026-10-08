# 第三方组件

本项目以 GPL-3.0-or-later 发布，完整文本见 [LICENSE](LICENSE)。

| 组件 | 用途与许可 | 对应源码 |
| --- | --- | --- |
| inode-njit | H3C 编码、AES/MD5 和字典，GPL-3.0；固定提交 `7e984256e20e5d6325643fb79daab895ffc6cad7` | `CampusTerminal/core/vendor/inode-njit/`，保留原始许可与归属 |
| PyQt5 5.15.10 | GUI，GPL v3；此公开构建使用 GPL 版本 | <https://www.riverbankcomputing.com/software/pyqt/download> |
| PyQt5-sip 12.20.0 | Python/Qt 绑定运行支持，BSD-2-Clause | <https://pypi.org/project/PyQt5-sip/12.20.0/> |
| Qt 5 | PyQt5 的动态链接库；当前构建环境为 Qt 5.15.2，保留所用发行物的 LGPL v3 许可，GPL 组件按 GPL v3 使用 | <https://download.qt.io/archive/qt/5.15/5.15.2/single/> |
| Python 3.13.5 | 打包后的解释器，PSF License | <https://www.python.org/downloads/release/python-3135/> |
| psutil 5.9.8 | 网卡与进程信息，BSD-3-Clause | <https://github.com/giampaolo/psutil/tree/release-5.9.8> |
| PyInstaller 6.22.3 | 打包器和 bootloader，GPL v2 或更新版本，带发行例外 | <https://github.com/pyinstaller/pyinstaller> |
| 思源黑体 | `SourceHanSansSC-Bold.otf`，SIL Open Font License 1.1 | <https://github.com/adobe-fonts/source-han-sans>；许可在 `CampusTerminal/gui/assets/fonts/OFL.txt` |
| Inno Setup | 安装包生成工具，不是应用运行依赖 | <https://github.com/jrsoftware/issrc> |

公开包不捆绑 Npcap 或 H3C 官方客户端安装包。Npcap 的免费版本通常不允许随产品再分发，详见 <https://npcap.com/oem/redist>。
认证核心校验 Npcap 1.89 的 DLL 哈希；升级驱动需要重新审查并更新固定值，不能直接替换版本。
启动器在本机缺失 Npcap 时从官网直接下载 1.89，经固定 SHA-256 校验后打开交互式安装窗口；下载缓存留在本机，不纳入公开发行包。

安装版和便携版均附带项目许可证、此声明、`licenses/` 中的依赖许可及字体许可证。发行时应同时提供此仓库对应版本的完整源码；
替换 Python、Qt 或其它打包依赖后，也应更新组件版本、许可和对应源码位置。
