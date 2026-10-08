// SPDX-License-Identifier: GPL-3.0-or-later
using System.Diagnostics;
using System.Net.NetworkInformation;
using System.Security.Principal;
using System.Threading;

namespace CampusAuth;

internal static class LiveGate
{
    public static bool Elevated()
    {
        using var identity = WindowsIdentity.GetCurrent();
        return new WindowsPrincipal(identity).IsInRole(WindowsBuiltInRole.Administrator);
    }

    public static bool OriginalGuiRunning() => AnyOriginal(TrialSafety.IsOriginalGui);

    public static bool OriginalSuiteRunning() => AnyOriginal(TrialSafety.IsOriginalSuite);

    // Exclusive 802.1X cares about protocol/service processes, not an orphan GUI/tray.
    public static bool OriginalClientRunning() => OriginalSuiteRunning();

    private static bool AnyOriginal(Func<string, bool> match)
    {
        var processes = Process.GetProcesses();
        try { return processes.Any(p => match(p.ProcessName)); }
        finally { foreach (var process in processes) process.Dispose(); }
    }

    public static TrialSnapshot Capture(Guid adapter, bool maintenanceOwned = false)
    {
        var matches = NetworkInterface.GetAllNetworkInterfaces()
            .Where(n => Guid.TryParse(n.Id.Trim('{', '}'), out var id) && id == adapter).ToArray();
        if (matches.Length != 1)
            return new(new TrialIdentity(adapter, "", "", "missing"), false, OriginalClientRunning(), maintenanceOwned,
                false, Elevated(), false);
        var nic = matches[0];
        var info = Adapters.Describe(nic);
        var identity = new TrialIdentity(adapter, info.Mac, info.Ipv4, Adapters.RouteKey(nic, info.Ipv4));
        return new(identity, nic.OperationalStatus == OperationalStatus.Up, OriginalClientRunning(),
            maintenanceOwned, Adapters.AlternativePath(adapter), Elevated(), info.Ipv4.Length > 0);
    }

    public static bool WaitUntilUp(Guid adapter, TimeSpan limit, CancellationToken token)
    {
        var deadline = DateTime.UtcNow + limit;
        while (true)
        {
            token.ThrowIfCancellationRequested();
            if (Capture(adapter, true).LinkUp) return true;
            if (DateTime.UtcNow >= deadline) return false;
            Thread.Sleep(200);
        }
    }
}
