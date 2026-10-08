// SPDX-License-Identifier: GPL-3.0-or-later
using System.Net.NetworkInformation;
using System.Runtime.InteropServices;

namespace CampusAuth;

// After 802.1X the link is often already Up, so Windows may have given up DHCP.
// Notify/renew the existing client; do not disable the NIC or change DNS/routes.
internal static class DhcpRenew
{
    [DllImport("dhcpcsvc.dll", CharSet = CharSet.Unicode)]
    private static extern uint DhcpNotifyConfigChange(string? server, string adapter, bool isNew,
        uint ipIndex, uint ip, uint mask, uint dhcp);

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct AdapterIndex
    {
        public int Index;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)]
        public string Name;
    }

    [DllImport("iphlpapi.dll", SetLastError = true)]
    private static extern int GetInterfaceInfo(IntPtr table, ref int size);

    [DllImport("iphlpapi.dll", CharSet = CharSet.Unicode)]
    private static extern int IpRenewAddress(ref AdapterIndex adapter);

    [DllImport("iphlpapi.dll", CharSet = CharSet.Unicode)]
    private static extern int IpReleaseAddress(ref AdapterIndex adapter);

    // GetInterfaceInfo names the adapter "\DEVICE\TCPIP_{GUID}". The bare GUID is rejected.
    internal static string IphlpapiName(string interfaceId)
    {
        string id = interfaceId.Trim();
        if (!id.StartsWith("{", StringComparison.Ordinal))
            id = "{" + id.Trim('{', '}') + "}";
        return @"\DEVICE\TCPIP_" + id.ToUpperInvariant();
    }

    // Prefer the name Windows itself reports for this ifIndex. The constructed
    // TCPIP path is only a fallback when GetInterfaceInfo cannot be read.
    internal static string AdapterName(int index, string interfaceId)
    {
        const int insufficient = 122;
        int size = 0;
        int first = GetInterfaceInfo(IntPtr.Zero, ref size);
        if ((first != 0 && first != insufficient) || size <= 8)
            return IphlpapiName(interfaceId);
        IntPtr buffer = Marshal.AllocHGlobal(size);
        try
        {
            if (GetInterfaceInfo(buffer, ref size) != 0) return IphlpapiName(interfaceId);
            int count = Marshal.ReadInt32(buffer);
            const int stride = 4 + 128 * 2;
            var cursor = buffer + 4;
            for (int i = 0; i < count && i < 64; i++)
            {
                int found = Marshal.ReadInt32(cursor);
                string name = Marshal.PtrToStringUni(cursor + 4, 128)?.TrimEnd('\0') ?? "";
                if (found == index && name.Length > 0) return name;
                cursor += stride;
            }
        }
        catch (Exception ex) when (ex is ArgumentException or AccessViolationException)
        {
            return IphlpapiName(interfaceId);
        }
        finally { Marshal.FreeHGlobal(buffer); }
        return IphlpapiName(interfaceId);
    }

    public static bool Request(Guid adapterId)
    {
        var id = "{" + adapterId.ToString().ToUpperInvariant() + "}";
        bool notified = false;
        try { notified = DhcpNotifyConfigChange(null, id, false, 0, 0, 0, 0) == 0; }
        catch (DllNotFoundException) { }
        bool renewed = false;
        try
        {
            var nic = NetworkInterface.GetAllNetworkInterfaces()
                .FirstOrDefault(n => Guid.TryParse(n.Id.Trim('{', '}'), out var found) && found == adapterId);
            if (nic != null)
            {
                int index = nic.GetIPProperties().GetIPv4Properties()?.Index ?? 0;
                if (index > 0)
                {
                    var map = new AdapterIndex { Index = index, Name = AdapterName(index, nic.Id) };
                    renewed = IpRenewAddress(ref map) == 0;
                }
            }
        }
        catch (Exception ex) when (ex is NetworkInformationException or DllNotFoundException or EntryPointNotFoundException) { }
        return notified || renewed;
    }

    public static bool Release(Guid adapterId)
    {
        try
        {
            var nic = NetworkInterface.GetAllNetworkInterfaces()
                .FirstOrDefault(n => Guid.TryParse(n.Id.Trim('{', '}'), out var found) && found == adapterId);
            if (nic == null) return false;
            int index = nic.GetIPProperties().GetIPv4Properties()?.Index ?? 0;
            if (index <= 0) return false;
            var map = new AdapterIndex { Index = index, Name = AdapterName(index, nic.Id) };
            return IpReleaseAddress(ref map) == 0;
        }
        catch (Exception ex) when (ex is NetworkInformationException or DllNotFoundException or EntryPointNotFoundException)
        {
            return false;
        }
    }
}
