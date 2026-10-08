// SPDX-License-Identifier: GPL-3.0-or-later
namespace CampusAuth;

internal sealed record TrialIdentity(Guid Adapter, string Mac, string Ipv4, string RouteKey);
internal sealed record TrialSnapshot(TrialIdentity Identity, bool LinkUp, bool OriginalClientRunning,
    bool MaintenanceOwned, bool AlternativePath, bool Elevated, bool AddressReady=true);

internal static class TrialSafety
{
    public static string? BlockReason(TrialIdentity expected, TrialSnapshot current, bool layer2Only=false)
    {
        if (!current.Elevated) return "ElevationRequired";
        if (!current.MaintenanceOwned) return "MaintenanceOwnershipLost";
        if (current.OriginalClientRunning) return "OriginalClientRunning";
        // Another real path (phone USB share) must win over "cable down" retries.
        // Otherwise the client keeps reauthenticating and the campus default route
        // stays preferred over the phone.
        if (current.AlternativePath) return "AlternativeNetworkPath";
        if (!current.LinkUp) return "LinkUnavailable";
        if (layer2Only)
        {
            if (current.Identity.Adapter != expected.Adapter || current.Identity.Mac != expected.Mac) return "InterfaceIdentityChanged";
        }
        else if (!current.AddressReady || current.Identity != expected) return "InterfaceIdentityChanged";
        return null;
    }

    internal static bool IsOriginalGui(string name) =>
        name.Equals("iNode Client", StringComparison.OrdinalIgnoreCase);

    internal static bool IsOriginalSuite(string name) =>
        name.Equals("iNodeMon", StringComparison.OrdinalIgnoreCase) ||
        name.Equals("iNodeCmn", StringComparison.OrdinalIgnoreCase) ||
        name.Equals("iNode1x", StringComparison.OrdinalIgnoreCase) ||
        name.Equals("iNodePortal", StringComparison.OrdinalIgnoreCase) ||
        name.Equals("iNodeSec", StringComparison.OrdinalIgnoreCase) ||
        name.Equals("iNodeImg", StringComparison.OrdinalIgnoreCase);

    internal static bool IsOriginalProcess(string name) => IsOriginalGui(name) || IsOriginalSuite(name);
}
