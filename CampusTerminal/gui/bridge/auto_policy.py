# SPDX-License-Identifier: GPL-3.0-or-later
import uuid

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


def adapter_key(value):
    """Canonical UUID text for an adapter id, or None for blank/invalid values."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return str(uuid.UUID(text))
    except (ValueError, AttributeError, TypeError):
        return None


def same_adapter(left, right):
    """Compare adapter identity by UUID value, ignoring case and braces."""
    a, b = adapter_key(left), adapter_key(right)
    return bool(a is not None and b is not None and a == b)


def adapter_identity_changed(previous, current):
    """A real NIC change: formatting-only differences are the same adapter."""
    return previous != current and not same_adapter(previous, current)


def resume_block_reason(owned, owned_adapter, adapter, auto_connect, auto_reconnect, other_network):
    """Why a slow retry may or may not ask the core to resume its session."""
    if not owned:
        return "not_owned"
    if not same_adapter(owned_adapter, adapter):
        return "adapter_mismatch"
    if not auto_connect:
        return "auto_connect_off"
    if not auto_reconnect:
        return "auto_reconnect_off"
    if other_network:
        return "other_network"
    return "ok"


def may_resume_owned_session(periodic, owned, owned_adapter, adapter, auto_connect, auto_reconnect, other_network):
    """Only a slow retry on the same adapter may ask the core to resume its session.

    The core re-checks the same ownership immediately before it touches iNode.
    """
    return bool(periodic and resume_block_reason(
        owned, owned_adapter, adapter, auto_connect, auto_reconnect, other_network) == "ok")


def apply_connect_outcome(error, phase, failure_count, yielded, other_network, counted=True):
    """Pure campaign accounting after a status/connect result.

    Returns (failure_count, retry_stopped, yielded, notice_error, suppress_error_toast).
    Count resets only after a verified online session. Pass counted=False when the
    failure_count was adopted from the core and already includes this error.
    """
    if other_network or error == "AlternativeNetworkPath":
        return failure_count, True, True, "AlternativeNetworkPath", False
    if phase in ("online", "degraded"):
        return 0, False, False, None, False
    if phase != "error" or not error:
        return failure_count, False, yielded, error, False
    count = failure_count + 1 if counted and counts_as_auto_failure(error) else failure_count
    if should_stop_auto_connect(error, count, False):
        notice = "AutoReconnectLimit" if count >= MAX_AUTO_FAILURES and counts_as_auto_failure(error) else error
        return count, True, yielded, notice, False
    return count, False, yielded, error, True
