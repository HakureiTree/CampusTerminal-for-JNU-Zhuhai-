# 发行包

每个版本放在独立目录，最新版本为 [1.4.1](1.4.1/README.md)，首个版本为 [1.3.18](1.3.18/README.md)。

- `CampusTerminal-<版本>-windows-x64-setup.exe`：Windows 安装版。
- `CampusTerminal-<版本>-windows-x64-portable.zip`：完整便携目录，解压后运行。
- `update-manifest.json` 和 `CampusTerminal-<版本>-windows-x64-payload.zip`：内置更新清单及完整文件包，从 1.4.1 开始提供。
- `SHA256SUMS.txt`：发行文件的 SHA-256 校验值。
- `SOURCE-SHA256SUMS.txt`：生成该版本时的公开源码及资源文件清单。
- `BUILD-ENVIRONMENT.txt`：该版本使用的编译工具及 Python 依赖版本。

安装、依赖和自主编译方法见仓库根目录 [README](../README.md)。发行包与对应源码应一起发布。
