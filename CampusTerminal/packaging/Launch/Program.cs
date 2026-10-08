using System;
using System.Diagnostics;
using System.IO;
using System.IO.Pipes;
using System.Net;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Threading;
using System.Windows.Forms;

namespace CampusLaunch;

internal static class Program
{
    const string HostTask = "ReInode-CampusTerminal-Host";
    const string DotnetUrl = "https://aka.ms/dotnet/10.0/windowsdesktop-runtime-win-x64.exe";

    [DllImport("kernel32.dll")] static extern bool AllocConsole();
    [DllImport("kernel32.dll")] static extern bool FreeConsole();
    [DllImport("kernel32.dll")] static extern IntPtr GetConsoleWindow();
    [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    static bool winFormsReady;

    static void EnsureWinForms()
    {
        if (winFormsReady) return;
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        winFormsReady = true;
    }

    [STAThread]
    static int Main(string[] args)
    {
        bool silent = HasArg(args, "--silent");
        bool setup = HasArg(args, "--setup");
        string here = AppDomain.CurrentDomain.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar);
        if (!setup)
        {
            GuiPresence already = DetectGui(here);
            if (already == GuiPresence.Same)
            {
                if (!silent) SignalReveal(here);
                return 0;
            }
            // Autostart must not pop a dialog over another copy. A manual launch still explains it.
            if (already == GuiPresence.Other)
            {
                if (silent) return 0;
                EnsureWinForms();
                MessageBox.Show("已经有另一份终端在运行。请先在右下角托盘退出那一份，再打开这一份。",
                    "开源暨珠有线网络终端");
                return 1;
            }
        }
        if (!silent || setup) OpenLog();
        Log("正在启动…");
        if (setup)
        {
            int code = RunSetup(here);
            Log(code == 0 ? "配置完成。" : "配置未完成。");
            return code;
        }
        Log("检查 Npcap 驱动…");
        bool npcap = NpcapReady();
        Log(npcap ? "  已就绪" : "  需要配置（检测驱动服务和两个 DLL）");
        Log("检查 .NET 桌面运行库…");
        bool dotnet = DotnetReady();
        Log(dotnet ? "  已就绪" : "  未安装");
        Log("检查后台任务…");
        bool task = HostTaskReady();
        Log(task ? "  已登记" : "  未登记（首次连接时再登记，不挡住启动）");
        if (!npcap || !dotnet)
        {
            Log("需要管理员权限进行一次性配置…");
            if (Elevated())
            {
                int code = RunSetup(here);
                if (code != 0) return code;
            }
            else if (!RelaunchElevated("--setup"))
            {
                EnsureWinForms();
                MessageBox.Show("需要管理员权限才能完成首次配置（驱动和运行库）。", "开源暨珠有线网络终端");
                return 1;
            }
        }
        string core = Path.Combine(here, "CampusTerminal.Core.exe");
        if (!File.Exists(core))
        {
            EnsureWinForms();
            MessageBox.Show("缺少 CampusTerminal.Core.exe。请重新解压完整压缩包，不要只拷贝启动器，也不要从压缩包内部直接运行。",
                "开源暨珠有线网络终端");
            return 1;
        }
        Log("启动界面…");
        int launched = LaunchGui(here, silent);
        ShowWindow(GetConsoleWindow(), 0);
        FreeConsole();
        return launched;
    }

    static void OpenLog()
    {
        AllocConsole();
        Console.Title = "开源暨珠有线网络终端 · 环境检查";
        try { Console.OutputEncoding = System.Text.Encoding.UTF8; } catch { }
        Console.Out.Flush();
    }

    static void Log(string line)
    {
        try
        {
            Console.WriteLine("[" + DateTime.Now.ToString("HH:mm:ss") + "] " + line);
            Console.Out.Flush();
        }
        catch { }
    }

    static bool HasArg(string[] args, string name)
    {
        return Array.Exists(args, a => string.Equals(a, name, StringComparison.OrdinalIgnoreCase));
    }

    static bool Elevated() =>
        new WindowsPrincipal(WindowsIdentity.GetCurrent()).IsInRole(WindowsBuiltInRole.Administrator);

    static WindowsNpcapPlatform NpcapPlatform() => new WindowsNpcapPlatform(
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "CampusTerminal", "installers"), Log);

    static bool NpcapReady() => NpcapPlatform().Detect() == NpcapState.Ready;

    static bool DotnetReady()
    {
        string shared = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
            "dotnet", "shared", "Microsoft.WindowsDesktop.App");
        if (!Directory.Exists(shared)) return false;
        foreach (var dir in Directory.GetDirectories(shared))
            if (Path.GetFileName(dir).StartsWith("10.", StringComparison.Ordinal)) return true;
        return false;
    }

    static bool HostTaskReady()
    {
        string want = Path.GetFullPath(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "CampusTerminal.Core.exe"));
        string command = HostTaskCommand();
        return command != null && string.Equals(Path.GetFullPath(command.Trim('"')), want, StringComparison.OrdinalIgnoreCase);
    }

    static string HostTaskCommand()
    {
        var psi = new ProcessStartInfo("schtasks.exe", "/Query /TN \"" + HostTask + "\" /XML")
        { UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true };
        try
        {
            using var p = Process.Start(psi);
            string xml = p.StandardOutput.ReadToEnd();
            p.WaitForExit(4000);
            if (p.ExitCode != 0) return null;
            int a = xml.IndexOf("<Command>", StringComparison.OrdinalIgnoreCase);
            int b = xml.IndexOf("</Command>", StringComparison.OrdinalIgnoreCase);
            if (a < 0 || b < 0) return null;
            return xml.Substring(a + 9, b - a - 9).Trim();
        }
        catch { return null; }
    }

    static bool RelaunchElevated(string argument)
    {
        try
        {
            var start = new ProcessStartInfo(Application.ExecutablePath)
            {
                UseShellExecute = true, Verb = "runas", Arguments = argument,
                WorkingDirectory = AppDomain.CurrentDomain.BaseDirectory
            };
            using var p = Process.Start(start);
            if (p == null) return false;
            p.WaitForExit();
            return p.ExitCode == 0;
        }
        catch { return false; }
    }

    static int RunSetup(string here)
    {
        try
        {
            string payload = Path.Combine(here, "payload");
            var npcapResult = new NpcapSetup(NpcapPlatform()).EnsureReady();
            if (npcapResult != NpcapSetupResult.Ready)
            {
                EnsureWinForms();
                string reason = npcapResult == NpcapSetupResult.Cancelled ? "已取消 Npcap 安装。完成安装后再打开终端。" :
                    npcapResult == NpcapSetupResult.RestartRequired ? "Npcap 安装器要求重启。请重启计算机后再打开终端。" :
                    npcapResult == NpcapSetupResult.Incompatible ? "检测到的 Npcap DLL 与本版支持的 1.89 不一致。请自行确认是否需要更换版本，启动器不会自动覆盖已有驱动。\n\n" + WindowsNpcapPlatform.InstallerUrl :
                    npcapResult == NpcapSetupResult.Unreadable ? "无法读取 Npcap 驱动或 DLL。请检查文件权限后重试。" :
                    "Npcap 安装未完成，驱动服务或 DLL 仍未就绪。请重试安装；本次不会启动认证。";
                Log(reason);
                MessageBox.Show(reason,
                    "开源暨珠有线网络终端", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return 1;
            }
            Log("结束其它位置的认证后台…");
            foreach (var p in Process.GetProcessesByName("CampusTerminal.Core"))
            {
                try { p.Kill(); p.WaitForExit(4000); } catch { }
                p.Dispose();
            }
            if (!DotnetReady())
            {
                Log("正在安装 .NET 桌面运行库…");
                string runtime = Path.Combine(payload, "windowsdesktop-runtime-win-x64.exe");
                if (!File.Exists(runtime))
                {
                    Log("本地没有运行库安装包，正在下载…");
                    runtime = DownloadDotnet(payload);
                }
                RunInstaller(runtime, "/install /quiet /norestart");
            }
            string core = Path.Combine(here, "CampusTerminal.Core.exe");
            string register = Path.Combine(here, "operations", "Register-HostTask.ps1");
            if (File.Exists(register) && File.Exists(core))
            {
                Log("正在登记后台任务…");
                Run("powershell.exe", "-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File \"" +
                    register + "\" -Exe \"" + core + "\"");
            }
            WriteShortcut(here);
            if (!NpcapReady())
                return OfferInode(here, "认证驱动未能安装。可以安装学校官方客户端作为应急联网。");
            if (!DotnetReady())
                return OfferInode(here, "未能安装 .NET 桌面运行库，本终端无法启动。可以安装学校官方客户端作为应急联网。");
            return 0;
        }
        catch (Exception ex)
        {
            Log("错误：" + ex.Message);
            EnsureWinForms();
            MessageBox.Show(ex.Message, "开源暨珠有线网络终端");
            return OfferInode(here, "本终端未能完成配置。可以安装学校官方客户端作为应急联网。");
        }
    }

    static int OfferInode(string root, string reason)
    {
        string setup = Path.Combine(root, "payload", "iNodeSetup.exe");
        if (!File.Exists(setup) || OriginalPresent()) return 1;
        EnsureWinForms();
        var choice = MessageBox.Show(reason + "\n\n是否打开学校官方客户端安装包？（可以拒绝）",
            "开源暨珠有线网络终端", MessageBoxButtons.YesNo, MessageBoxIcon.Question);
        if (choice == DialogResult.Yes)
            Process.Start(new ProcessStartInfo(setup) { UseShellExecute = true });
        return 1;
    }

    static bool OriginalPresent() =>
        File.Exists(@"C:\Program Files (x86)\iNode\iNode Client\iNode Client.exe");

    static void RunInstaller(string exe, string args)
    {
        if (string.IsNullOrEmpty(exe) || !File.Exists(exe)) throw new InvalidOperationException("缺少安装包：" + exe);
        Run(exe, args);
    }

    static void Run(string file, string args)
    {
        var psi = new ProcessStartInfo(file, args) { UseShellExecute = false, CreateNoWindow = true };
        using var p = Process.Start(psi);
        if (p == null) throw new InvalidOperationException("无法启动 " + file);
        p.WaitForExit();
        if (p.ExitCode != 0 && p.ExitCode != 3010) throw new InvalidOperationException(Path.GetFileName(file) + " 退出码 " + p.ExitCode);
    }

    static string DownloadDotnet(string payload)
    {
        Directory.CreateDirectory(payload);
        string dest = Path.Combine(payload, "windowsdesktop-runtime-win-x64.exe");
        ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;
        using var client = new WebClient();
        client.DownloadFile(DotnetUrl, dest);
        return dest;
    }

    static void WriteShortcut(string target)
    {
        string launcher = Path.Combine(target, "开源暨珠有线网络终端.exe");
        if (!File.Exists(launcher)) return;
        string desktop = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),
            "开源暨珠有线网络终端.lnk");
        var t = Type.GetTypeFromProgID("WScript.Shell");
        dynamic shell = Activator.CreateInstance(t);
        var link = shell.CreateShortcut(desktop);
        link.TargetPath = launcher;
        link.WorkingDirectory = target;
        link.WindowStyle = 1;
        link.IconLocation = launcher + ",0";
        link.Save();
    }

    static void SignalReveal(string root)
    {
        try
        {
            using var pipe = new NamedPipeClientStream(".", "CampusTerminal.window." + Environment.UserName, PipeDirection.Out);
            pipe.Connect(400);
            pipe.WriteByte((byte)'1');
            pipe.Flush();
            return;
        }
        catch { }
        string gui = Path.Combine(root, "CampusTerminal.exe");
        if (!File.Exists(gui)) return;
        try
        {
            Process.Start(new ProcessStartInfo(gui) { WorkingDirectory = root, UseShellExecute = true });
        }
        catch { }
    }

    static int LaunchGui(string root, bool silent)
    {
        string gui = Path.Combine(root, "CampusTerminal.exe");
        if (!File.Exists(gui))
        {
            EnsureWinForms();
            MessageBox.Show("找不到 CampusTerminal.exe。", "开源暨珠有线网络终端");
            return 1;
        }
        using var gate = new Mutex(false, "Local\\CampusTerminal.GuiStart");
        bool owned = false;
        try
        {
            try { owned = gate.WaitOne(8000); }
            catch (AbandonedMutexException) { owned = true; }
            if (!owned) return silent ? 0 : 1;
            if (DetectGui(root) != GuiPresence.None)
            {
                if (!silent) SignalReveal(root);
                return 0;
            }
            Process.Start(new ProcessStartInfo(gui)
            {
                WorkingDirectory = root,
                UseShellExecute = true,
                Arguments = silent ? "--silent" : ""
            });
            return 0;
        }
        finally { if (owned) gate.ReleaseMutex(); }
    }

    enum GuiPresence { None, Same, Other }

    static GuiPresence DetectGui(string here)
    {
        string want = Path.GetFullPath(Path.Combine(here, "CampusTerminal.exe"));
        var list = Process.GetProcessesByName("CampusTerminal");
        if (list.Length == 0) return GuiPresence.None;
        bool sawOther = false;
        bool sawUnknown = false;
        foreach (var p in list)
        {
            try
            {
                string path = p.MainModule?.FileName;
                if (string.IsNullOrEmpty(path)) { sawUnknown = true; continue; }
                if (string.Equals(Path.GetFullPath(path), want, StringComparison.OrdinalIgnoreCase))
                    return GuiPresence.Same;
                sawOther = true;
            }
            catch { sawUnknown = true; }
            finally { p.Dispose(); }
        }
        if (sawOther) return GuiPresence.Other;
        return sawUnknown ? GuiPresence.Same : GuiPresence.None;
    }
}
