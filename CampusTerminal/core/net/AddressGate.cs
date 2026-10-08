// SPDX-License-Identifier: GPL-3.0-or-later
using System.Net;
using System.Net.Sockets;

namespace CampusAuth;

// Authentication needs Ethernet, not an existing IP lease. Once acquired after
// EAP Success, the address and route become immutable for this bounded trial.
internal sealed class TrialAddressGate(TrialIdentity original)
{
    public bool Authenticated { get; private set; }
    public TrialIdentity? BoundIdentity { get; private set; }
    public void MarkAuthenticated() => Authenticated = true;
    public string? Observe(TrialSnapshot snapshot)
    {
        var blocked = TrialSafety.BlockReason(BoundIdentity ?? original, snapshot, BoundIdentity == null);
        if (blocked != null) return blocked;
        if (Authenticated && BoundIdentity == null && snapshot.AddressReady && UsableIpv4(snapshot.Identity.Ipv4))
            BoundIdentity = snapshot.Identity;
        return null;
    }
    internal static bool UsableIpv4(string text)
    {
        if (!IPAddress.TryParse(text, out var address) || address.AddressFamily != AddressFamily.InterNetwork) return false;
        var bytes = address.GetAddressBytes();
        return bytes[0] != 0 && bytes[0] != 127 && bytes[0] < 224 && !(bytes[0] == 169 && bytes[1] == 254);
    }
}
