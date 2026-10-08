// SPDX-License-Identifier: GPL-3.0-or-later
using System.Diagnostics;
using System.Net.NetworkInformation;
using System.Text;

namespace CampusAuth;

// Npcap's filter attaches to every new Ethernet miniport, including a phone's
// Remote NDIS adapter, and that attachment makes USB tethering fail to turn on.
// The campus port keeps the filter. Only phone-tether adapters are unbound.
internal static class TetherBinding
{
    private static int busy;
    private static int started;
    private static Timer? timer;
    private static bool? elevated;
    private static DateTime lastDeep = DateTime.MinValue;
    private static readonly DateTime StartedAt = DateTime.UtcNow;
    private static readonly object Gate = new();
    private static readonly Dictionary<string, DateTime> Seen = new(StringComparer.OrdinalIgnoreCase);
    private static readonly HashSet<string> Done = new(StringComparer.OrdinalIgnoreCase);

    public static void Start(CancellationToken token)
    {
        if (Interlocked.Exchange(ref started, 1) == 1) return;
        try { NetworkChange.NetworkAddressChanged += (_, _) => Sweep(); }
        catch (Exception) { }
        timer = new Timer(_ => Sweep(), null, TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(1));
        token.Register(() => timer?.Dispose());
    }

    public static void Sweep()
    {
        if (!OperatingSystem.IsWindows()) return;
        if (Interlocked.Exchange(ref busy, 1) == 1) return;
        try
        {
            if (!Elevated()) return;
            var pending = Pending();
            if (pending.Count > 0 && Unbind(pending.Select(item => item.Name)))
                Mark(pending);
            var interval = DateTime.UtcNow - StartedAt < TimeSpan.FromMinutes(2)
                ? TimeSpan.FromSeconds(3) : TimeSpan.FromSeconds(20);
            if (DateTime.UtcNow - lastDeep >= interval)
            {
                lastDeep = DateTime.UtcNow;
                Deep();
            }
        }
        catch (Exception) { }
        finally { Interlocked.Exchange(ref busy, 0); }
    }

    private static bool Elevated()
    {
        elevated ??= LiveGate.Elevated();
        return elevated.Value;
    }

    private readonly record struct Nic(string Id, string Name);

    private static List<Nic> Pending()
    {
        var live = new List<Nic>();
        foreach (var nic in NetworkInterface.GetAllNetworkInterfaces())
        {
            if (!Adapters.IsPhoneTether(nic.Description, nic.Name) || string.IsNullOrWhiteSpace(nic.Name)) continue;
            live.Add(new(nic.Id, nic.Name));
        }
        var liveIds = new HashSet<string>(live.Select(item => item.Id), StringComparer.OrdinalIgnoreCase);
        lock (Gate)
        {
            foreach (var id in Done.Where(id => !liveIds.Contains(id)).ToArray())
            {
                Done.Remove(id);
                Seen.Remove(id);
            }
            var pending = new List<Nic>();
            foreach (var nic in live)
            {
                if (Done.Contains(nic.Id)) continue;
                if (!Seen.ContainsKey(nic.Id)) Seen[nic.Id] = DateTime.UtcNow;
                pending.Add(nic);
            }
            return pending;
        }
    }

    private static void Mark(List<Nic> pending)
    {
        var now = DateTime.UtcNow;
        lock (Gate)
            foreach (var nic in pending)
                if (Seen.TryGetValue(nic.Id, out var at) && now - at >= TimeSpan.FromSeconds(20))
                    Done.Add(nic.Id);
    }

    private static bool Unbind(IEnumerable<string> names)
    {
        string packed = Convert.ToBase64String(Encoding.UTF8.GetBytes(string.Join("\n", names)));
        const string script = """
            $ErrorActionPreference = 'Stop'
            $raw = [Environment]::GetEnvironmentVariable('CAMPUS_TETHER_NAMES')
            if (-not $raw) { exit 0 }
            $decoded = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($raw))
            foreach ($name in ($decoded -split "`n")) {
              if (-not $name) { continue }
              $rows = @(Get-NetAdapterBinding -Name $name -ErrorAction SilentlyContinue | Where-Object {
                $_.Enabled -and ($_.ComponentID -match 'npcap|npf' -or $_.DisplayName -match 'Npcap|WinPcap') })
              foreach ($row in $rows) {
                Disable-NetAdapterBinding -Name $name -ComponentID $row.ComponentID -Confirm:$false
              }
            }
            exit 0
            """;
        return Run(script, packed);
    }

    private static void Deep()
    {
        const string script = """
            $ErrorActionPreference = 'Stop'
            $pattern = 'rndis|remote ndis|iphone|apple mobile|tether|android|personal hotspot|internet sharing|mobile device|mobile connect|cdc ncm|usb ncm'
            $skip = 'loopback|virtual|hyper-v|vpn|tap-windows|wintun|clash|teredo|isatap|bluetooth|wan miniport'
            $nics = @(Get-NetAdapter -IncludeHidden -ErrorAction SilentlyContinue | Where-Object {
              $text = ($_.InterfaceDescription + ' ' + $_.Name).ToLowerInvariant()
              $text -match $pattern -and $text -notmatch $skip })
            foreach ($nic in $nics) {
              $rows = @(Get-NetAdapterBinding -Name $nic.Name -ErrorAction SilentlyContinue | Where-Object {
                $_.Enabled -and ($_.ComponentID -match 'npcap|npf' -or $_.DisplayName -match 'Npcap|WinPcap') })
              foreach ($row in $rows) {
                Disable-NetAdapterBinding -Name $nic.Name -ComponentID $row.ComponentID -Confirm:$false
              }
            }
            exit 0
            """;
        Run(script, null);
    }

    private static bool Run(string script, string? names)
    {
        var start = new ProcessStartInfo("powershell.exe", "-NoProfile -NonInteractive -ExecutionPolicy Bypass -Command -")
        {
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardInput = true
        };
        if (!string.IsNullOrEmpty(names)) start.Environment["CAMPUS_TETHER_NAMES"] = names;
        using var process = Process.Start(start);
        if (process == null) return false;
        process.StandardInput.Write(script);
        process.StandardInput.Close();
        if (!process.WaitForExit(8000))
        {
            try { process.Kill(entireProcessTree: true); } catch (Exception) { }
            return false;
        }
        return process.ExitCode == 0;
    }
}
