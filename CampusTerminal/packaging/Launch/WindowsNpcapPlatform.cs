// SPDX-License-Identifier: GPL-3.0-or-later
using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using Microsoft.Win32;

namespace CampusLaunch;

internal sealed class WindowsNpcapPlatform : INpcapSetupPlatform
{
    internal const string InstallerUrl = "https://npcap.com/dist/npcap-1.89.exe";
    // Official 1.89 installer, Authenticode publisher: Nmap Software LLC.
    internal const string InstallerSha256 = "8AED85E900D783D1308506E919587D3E540451947AF8A82F2D04F819E44305CC";
    internal const string InstallerArguments = "/admin_only=enforced /winpcap_mode=disabled /dot11_support=disabled /loopback_support=disabled /no_kill=yes";
    const int MaximumInstallerBytes = 10 * 1024 * 1024;
    readonly string cacheDirectory;
    readonly Action<string> log;

    public WindowsNpcapPlatform(string cacheDirectory, Action<string> log)
    {
        this.cacheDirectory = cacheDirectory;
        this.log = log;
    }

    public NpcapState Detect()
    {
        try
        {
            using var key = Registry.LocalMachine.OpenSubKey(@"SYSTEM\CurrentControlSet\Services\npcap");
            string libraries = Path.Combine(Environment.SystemDirectory, "Npcap");
            return NpcapEnvironment.Evaluate(key != null,
                NpcapEnvironment.HashFile(Path.Combine(libraries, "wpcap.dll")),
                NpcapEnvironment.HashFile(Path.Combine(libraries, "Packet.dll")));
        }
        catch (Exception ex) when (ex is IOException || ex is UnauthorizedAccessException || ex is System.Security.SecurityException)
        {
            log("无法读取 Npcap 环境：" + ex.Message);
            return NpcapState.Unreadable;
        }
    }

    public string PrepareInstaller()
    {
        Directory.CreateDirectory(cacheDirectory);
        string destination = Path.Combine(cacheDirectory, "npcap-1.89.exe");
        if (string.Equals(NpcapEnvironment.HashFile(destination), InstallerSha256, StringComparison.OrdinalIgnoreCase))
        {
            log("使用已校验的 Npcap 1.89 安装包。");
            return destination;
        }

        log("未安装完整的 Npcap 环境，正在从官方网站下载 Npcap 1.89…");
        string temporary = destination + "." + Guid.NewGuid().ToString("N") + ".partial";
        try
        {
            ServicePointManager.SecurityProtocol |= SecurityProtocolType.Tls12;
            var request = (HttpWebRequest)WebRequest.Create(InstallerUrl);
            request.Timeout = 60000;
            request.ReadWriteTimeout = 60000;
            request.UserAgent = "CampusTerminal/1.3.18";
            using (var response = (HttpWebResponse)request.GetResponse())
            using (var input = response.GetResponseStream())
            using (var output = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            {
                if (response.ContentLength > MaximumInstallerBytes) throw new IOException("Npcap 安装包大小异常。");
                var buffer = new byte[81920];
                int count;
                long total = 0;
                var elapsed = Stopwatch.StartNew();
                while ((count = input.Read(buffer, 0, buffer.Length)) != 0)
                {
                    total += count;
                    if (total > MaximumInstallerBytes || elapsed.ElapsedMilliseconds > 120000)
                        throw new IOException("Npcap 下载超时或安装包大小异常。");
                    output.Write(buffer, 0, count);
                }
            }
            if (!string.Equals(NpcapEnvironment.HashFile(temporary), InstallerSha256, StringComparison.OrdinalIgnoreCase))
                throw new IOException("Npcap 安装包校验失败，未运行该文件。请重试或从官方网站手动安装 Npcap 1.89。");
            if (File.Exists(destination)) File.Delete(destination);
            File.Move(temporary, destination);
            log("Npcap 安装包 SHA-256 校验通过。");
            return destination;
        }
        catch (WebException ex)
        {
            throw new IOException("无法下载 Npcap。请先接入可用网络（例如手机共享），再重新启动终端；也可手动安装：" +
                InstallerUrl, ex);
        }
        finally
        {
            if (File.Exists(temporary)) File.Delete(temporary);
        }
    }

    public int ShowInstaller(string path)
    {
        // Keep the verified file locked against modification until the installer exits.
        using var locked = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        if (!string.Equals(NpcapEnvironment.Hash(locked), InstallerSha256, StringComparison.OrdinalIgnoreCase))
            throw new IOException("Npcap 安装包校验失败，未运行该文件。");
        log("正在打开 Npcap 安装窗口。请阅读许可并完成安装；WinPcap 兼容模式已禁用。");
        using var process = Process.Start(new ProcessStartInfo(path, InstallerArguments) { UseShellExecute = true });
        if (process == null) throw new IOException("无法打开 Npcap 安装窗口。");
        process.WaitForExit();
        log("Npcap 安装器退出码：" + process.ExitCode);
        return process.ExitCode;
    }
}
