// SPDX-License-Identifier: GPL-3.0-or-later
using System;
using System.IO;
using System.Text;
using CampusLaunch;

internal static class Program
{
    static int checks;

    static int Main(string[] args)
    {
        try
        {
            EnvironmentChecks();
            WorkflowChecks();
            FileChecks();
            if (args.Length == 2 && args[0] == "--download-official")
            {
                // Explicit integration check: downloads only, never installs a driver.
                var platform = new WindowsNpcapPlatform(Path.GetFullPath(args[1]), Console.WriteLine);
                string path = platform.PrepareInstaller();
                Equal(WindowsNpcapPlatform.InstallerSha256, NpcapEnvironment.HashFile(path), "official download integrity");
                Equal(path, platform.PrepareInstaller(), "verified cache reused");
            }
            Console.WriteLine("PASS " + checks + " launcher checks (no driver installed)");
            return 0;
        }
        catch (Exception ex) { Console.Error.WriteLine(ex); return 1; }
    }

    static void EnvironmentChecks()
    {
        string wpcap = NpcapEnvironment.WpcapSha256, packet = NpcapEnvironment.PacketSha256;
        Equal(NpcapState.Missing, NpcapEnvironment.Evaluate(false, null, null), "no Npcap");
        Equal(NpcapState.Missing, NpcapEnvironment.Evaluate(true, null, null), "service alone is insufficient");
        Equal(NpcapState.Missing, NpcapEnvironment.Evaluate(false, wpcap, packet), "DLLs alone are insufficient");
        Equal(NpcapState.Missing, NpcapEnvironment.Evaluate(true, wpcap, null), "missing Packet DLL");
        Equal(NpcapState.Missing, NpcapEnvironment.Evaluate(true, null, packet), "missing wpcap DLL");
        Equal(NpcapState.Ready, NpcapEnvironment.Evaluate(true, wpcap, packet), "supported DLLs and service");
        Equal(NpcapState.Ready, NpcapEnvironment.Evaluate(true, wpcap.ToLowerInvariant(), packet.ToLowerInvariant()), "hash case");
        Equal(NpcapState.Incompatible, NpcapEnvironment.Evaluate(true, "changed", packet), "changed wpcap");
        Equal(NpcapState.Incompatible, NpcapEnvironment.Evaluate(true, wpcap, "changed"), "changed Packet DLL");
        Equal(NpcapState.Incompatible, NpcapEnvironment.Evaluate(false, "changed", null), "preserve partial incompatible installation");
        Equal(64, wpcap.Length, "wpcap SHA-256 length");
        Equal(64, packet.Length, "Packet SHA-256 length");
        Equal(64, WindowsNpcapPlatform.InstallerSha256.Length, "installer SHA-256 length");
        Equal(false, WindowsNpcapPlatform.InstallerArguments.Contains("/S "), "interactive install");
        Equal(true, WindowsNpcapPlatform.InstallerArguments.Contains("/winpcap_mode=disabled"), "disable WinPcap compatibility");
        Equal(false, WindowsNpcapPlatform.InstallerArguments.Contains("/force"), "no forced replacement");
    }

    static void WorkflowChecks()
    {
        CheckFlow(NpcapState.Ready, NpcapState.Ready, 0, NpcapSetupResult.Ready, "detect");
        CheckFlow(NpcapState.Incompatible, NpcapState.Ready, 0, NpcapSetupResult.Incompatible, "detect");
        CheckFlow(NpcapState.Unreadable, NpcapState.Ready, 0, NpcapSetupResult.Unreadable, "detect");
        CheckFlow(NpcapState.Missing, NpcapState.Ready, 0, NpcapSetupResult.Ready, "detect,prepare,show,detect");
        CheckFlow(NpcapState.Missing, NpcapState.Missing, 0, NpcapSetupResult.Failed, "detect,prepare,show,detect");
        CheckFlow(NpcapState.Missing, NpcapState.Incompatible, 0, NpcapSetupResult.Failed, "detect,prepare,show,detect");
        CheckFlow(NpcapState.Missing, NpcapState.Ready, 1, NpcapSetupResult.Cancelled, "detect,prepare,show");
        CheckFlow(NpcapState.Missing, NpcapState.Ready, 3010, NpcapSetupResult.RestartRequired, "detect,prepare,show");
        CheckFlow(NpcapState.Missing, NpcapState.Missing, 350, NpcapSetupResult.RestartRequired, "detect,prepare,show");
        CheckFlow(NpcapState.Missing, NpcapState.Ready, 2, NpcapSetupResult.Ready, "detect,prepare,show,detect");
        CheckFlow(NpcapState.Missing, NpcapState.Missing, 2, NpcapSetupResult.Failed, "detect,prepare,show,detect");
        CheckFlow(NpcapState.Missing, NpcapState.Ready, 1618, NpcapSetupResult.Failed, "detect,prepare,show,detect");
        var failedDownload = new FakePlatform { ThrowOnPrepare = true };
        Throws<IOException>(() => new NpcapSetup(failedDownload).EnsureReady(), "download or integrity failure propagated");
        Equal("detect,prepare", failedDownload.Calls, "failed download never opens installer");
    }

    static void FileChecks()
    {
        using (var input = new MemoryStream(Encoding.ASCII.GetBytes("abc")))
            Equal("BA7816BF8F01CFEA414140DE5DAE2223B00361A396177A9CB410FF61F20015AD", NpcapEnvironment.Hash(input), "known SHA-256 vector");
        string temporary = Path.Combine(Path.GetTempPath(), "CampusTerminal-launcher-tests-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(temporary);
        try
        {
            Equal(null, NpcapEnvironment.HashFile(Path.Combine(temporary, "missing")), "missing file");
            string corrupt = Path.Combine(temporary, "npcap-1.89.exe");
            File.WriteAllText(corrupt, "corrupt cache");
            var platform = new WindowsNpcapPlatform(temporary, _ => { });
            Throws<IOException>(() => platform.ShowInstaller(corrupt), "reject changed installer before execution");
            using (var locked = new FileStream(corrupt, FileMode.Open, FileAccess.Read, FileShare.Read))
                Throws<IOException>(() => File.WriteAllText(corrupt, "modified"), "verified handle prevents concurrent replacement");
        }
        finally { Directory.Delete(temporary, true); }
    }

    static void CheckFlow(NpcapState before, NpcapState after, int exit, NpcapSetupResult expected, string calls)
    {
        var platform = new FakePlatform { Before = before, After = after, Exit = exit };
        Equal(expected, new NpcapSetup(platform).EnsureReady(), "setup result " + expected + "/" + exit);
        Equal(calls, platform.Calls, "setup sequence " + expected + "/" + exit);
    }

    static void Equal<T>(T expected, T actual, string name)
    {
        if (!Equals(expected, actual)) throw new Exception(name + ": expected " + expected + ", got " + actual);
        checks++;
    }

    static void Throws<T>(Action action, string name) where T : Exception
    {
        try { action(); } catch (T) { checks++; return; }
        throw new Exception(name + ": expected " + typeof(T).Name);
    }

    sealed class FakePlatform : INpcapSetupPlatform
    {
        public NpcapState Before = NpcapState.Missing, After = NpcapState.Ready;
        public int Exit;
        public bool ThrowOnPrepare;
        public string Calls = "";
        int detections;
        void Record(string call) => Calls += (Calls.Length == 0 ? "" : ",") + call;
        public NpcapState Detect() { Record("detect"); return detections++ == 0 ? Before : After; }
        public string PrepareInstaller()
        {
            Record("prepare");
            if (ThrowOnPrepare) throw new IOException("simulated failure");
            return "verified-installer.exe";
        }
        public int ShowInstaller(string path)
        {
            if (path != "verified-installer.exe") throw new Exception("wrong installer");
            Record("show"); return Exit;
        }
    }
}
