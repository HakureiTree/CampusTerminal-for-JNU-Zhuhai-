// SPDX-License-Identifier: GPL-3.0-or-later
namespace CampusAuth;

internal static class ConnectionRetryPolicy
{
    internal const int MaxAttempts = 3;
    // EAP start through MD5/Success. DHCP wait and HTTPS verification have their own budgets.
    internal static readonly TimeSpan AttemptTimeout = TimeSpan.FromSeconds(6);
    internal static readonly TimeSpan AddressWaitTimeout = TimeSpan.FromSeconds(45);
    internal static readonly TimeSpan VerificationTimeout = TimeSpan.FromSeconds(20);

    internal static bool Retryable(string reason) => reason is "ConnectionAttemptTimeout" or
        "AuthenticatedAddressTimeout" or "RecoveryRequested" or "RecoveryVerificationFailed" or
        "ConnectivityVerificationTimeout";

    internal static bool KeepAuthenticatedSession(string reason) => reason is "CampusDnsFailure" or
        "CampusPartlyReachable" or "ProbeIndeterminate";
}
