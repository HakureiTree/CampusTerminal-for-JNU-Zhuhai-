# SPDX-License-Identifier: GPL-3.0-or-later
MAX_AUTO_FAILURES = 5
SILENT_RETRY_SECONDS = 600

AUTO_RETRY = frozenset({
    "BackendMissing",
    "BackendUnavailable",
    "BackendLaunchFailed",
    "BackendStartTimeout",
    "AdapterNotFound",
    "LinkUnavailable",
    "OriginalClientRunning",
    "AuthenticationRejected",
    "ProtocolFailed",
    "ConnectionAttemptTimeout",
    "AuthenticatedAddressTimeout",
    "RecoveryVerificationFailed",
    "ConnectivityVerificationTimeout",
    "AuthenticationTimeout",
})

STOP_NOW = frozenset({
    "UnsupportedCredentialEncoding",
    "ElevationCancelled",
    "OriginalManualExitRequired",
    "MaintenanceAlreadyOwned",
    "HandoffFailed",
    "AutoReconnectLimit",
    "AlternativeNetworkPath",
    "ReconnectAttemptsExhausted",
})

COUNT_FAILURE = frozenset({
    "AuthenticationRejected",
    "ProtocolFailed",
    "ConnectionAttemptTimeout",
    "ReconnectAttemptsExhausted",
    "AuthenticatedAddressTimeout",
    "RecoveryVerificationFailed",
    "ConnectivityVerificationTimeout",
    "AuthenticationTimeout",
})


def connection_due(previous_up, current_up, enabled, manual_stop):
    return bool(enabled and not manual_stop and current_up and not previous_up)


def want_auto_connect(enabled, manual_stop, handed_back, has_adapter, has_credentials=True):
    # 802.1X must start before Windows reports the NIC as "up". Waiting for isup
    # deadlocks behind the official client, which is what brings the link up.
    # has_credentials must be saved account+password, not in-progress typing.
    return bool(enabled and not manual_stop and not handed_back and has_adapter and has_credentials)


def counts_as_auto_failure(error):
    return error in COUNT_FAILURE


def should_stop_auto_connect(error, failure_count=0, other_network=False):
    if other_network or error in STOP_NOW:
        return True
    return failure_count >= MAX_AUTO_FAILURES


def should_retry_auto_connect(error, enabled, manual_stop, handed_back, failure_count=0, other_network=False):
    if not want_auto_connect(enabled, manual_stop, handed_back, True, True):
        return False
    if should_stop_auto_connect(error, failure_count, other_network):
        return False
    return error in AUTO_RETRY


def silent_retry_wait(remaining, capped, other_network, enabled, manual_stop, handed_back):
    """After the fast cap, wait 10 minutes. USB and other networks pause the timer."""
    if not capped or other_network or not enabled or manual_stop or handed_back:
        return False, remaining
    if remaining > 1:
        return False, remaining - 1
    return True, SILENT_RETRY_SECONDS


def apply_connect_outcome(error, phase, failure_count, yielded, other_network):
    """Pure campaign accounting after a status/connect result.

    Returns (failure_count, retry_stopped, yielded, notice_error, suppress_error_toast).
    Count resets only after a verified online session.
    """
    if other_network or error == "AlternativeNetworkPath":
        return failure_count, True, True, "AlternativeNetworkPath", False
    if phase in ("online", "degraded"):
        return 0, False, False, None, False
    if phase != "error" or not error:
        return failure_count, False, yielded, error, False
    count = failure_count + 1 if counts_as_auto_failure(error) else failure_count
    if should_stop_auto_connect(error, count, False):
        notice = "AutoReconnectLimit" if count >= MAX_AUTO_FAILURES and counts_as_auto_failure(error) else error
        return count, True, yielded, notice, False
    return count, False, yielded, error, True
