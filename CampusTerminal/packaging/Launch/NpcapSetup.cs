// SPDX-License-Identifier: GPL-3.0-or-later
using System;
using System.IO;
using System.Security.Cryptography;

namespace CampusLaunch;

internal enum NpcapState { Missing, Ready, Incompatible, Unreadable }
internal enum NpcapSetupResult { Ready, Cancelled, RestartRequired, Failed, Incompatible, Unreadable }

internal interface INpcapSetupPlatform
{
    NpcapState Detect();
    string PrepareInstaller();
    int ShowInstaller(string path);
}

// The workflow has no registry, network or process dependencies of its own.
internal sealed class NpcapSetup
{
    readonly INpcapSetupPlatform platform;
    public NpcapSetup(INpcapSetupPlatform platform) => this.platform = platform;

    public NpcapSetupResult EnsureReady()
    {
        var state = platform.Detect();
        if (state == NpcapState.Ready) return NpcapSetupResult.Ready;
        if (state == NpcapState.Incompatible) return NpcapSetupResult.Incompatible;
        if (state == NpcapState.Unreadable) return NpcapSetupResult.Unreadable;

        string installer = platform.PrepareInstaller();
        int exitCode = platform.ShowInstaller(installer);
        if (exitCode == 1) return NpcapSetupResult.Cancelled;
        if (exitCode == 3010 || exitCode == 350) return NpcapSetupResult.RestartRequired;
        // Npcap documents exit code 2 for script aborts; inspect the environment as well.
        state = platform.Detect();
        if (state == NpcapState.Ready && (exitCode == 0 || exitCode == 2))
            return NpcapSetupResult.Ready;
        return NpcapSetupResult.Failed;
    }
}

internal static class NpcapEnvironment
{
    internal const string WpcapSha256 = "AA2C63A5A0B732E2AAEC6660F5D97727D857FCFD315084940859E5FE71A65C24";
    internal const string PacketSha256 = "1181BA48394DFD64E281D43850E41355BD6A0ED2523819980820221C0BE09D74";

    public static NpcapState Evaluate(bool serviceInstalled, string wpcapHash, string packetHash)
    {
        if ((wpcapHash != null && !string.Equals(wpcapHash, WpcapSha256, StringComparison.OrdinalIgnoreCase)) ||
            (packetHash != null && !string.Equals(packetHash, PacketSha256, StringComparison.OrdinalIgnoreCase)))
            return NpcapState.Incompatible;
        return serviceInstalled && wpcapHash != null && packetHash != null ? NpcapState.Ready : NpcapState.Missing;
    }

    public static string Hash(Stream stream)
    {
        using var sha = SHA256.Create();
        return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "");
    }

    public static string HashFile(string path)
    {
        if (!File.Exists(path)) return null;
        using var stream = File.OpenRead(path);
        return Hash(stream);
    }
}
