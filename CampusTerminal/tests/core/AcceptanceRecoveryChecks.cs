// SPDX-License-Identifier: GPL-3.0-or-later
using System.Text.Json.Nodes;
using CampusAuth;

internal static class AcceptanceRecoveryChecks
{
    internal static void Run(Action<bool, string> check)
    {
        var owner = new JsonObject { ["BackendPid"] = 123, ["BackendStartedUtc"] = "backend-start" };
        JsonNode[] helpers = [new JsonObject { ["ProcessId"] = 456, ["StartedUtc"] = "helper-start" }];
        string? Failure(int expected, Func<int, string, bool> alive)
        {
            try { AcceptanceRecovery.AssertStopped(owner, expected, helpers, alive); return null; }
            catch (InvalidOperationException ex) { return ex.Message; }
        }
        check(Failure(999, (_, _) => false) == "RecoveryBackendIdentityMismatch", "Recovery requires the owned backend identity");
        check(Failure(123, (pid, started) => pid == 123 && started == "backend-start") == "RecoveryBackendStillRunning",
            "Unresponsive live backend cannot be replaced");
        check(Failure(123, (pid, started) => pid == 456 && started == "helper-start") == "RecoveryHelperStillRunning",
            "Backend death does not authorize concurrent helper restoration");
        check(Failure(123, (_, _) => false) == null, "Only confirmed stopped processes admit crash recovery");
        bool uncertaintyPropagated = false;
        try { Failure(123, (_, _) => throw new IOException("IdentityUnavailable")); }
        catch (IOException) { uncertaintyPropagated = true; }
        check(uncertaintyPropagated, "Process-query failure is not evidence of death");

        string root = Path.Combine(Path.GetTempPath(), "campus-adopt-test-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        string path = Path.Combine(root, "pause-recovery.signal");
        try
        {
            File.WriteAllText(path, "CampusTerminal-existing");
            using (var lease = new ObserverLease(root, "CampusTerminal-existing"))
                check(lease.IsOwned && lease.Preserve, "Adopted pause is preserved by default");
            check(File.Exists(path), "Disposing an unverified recovery does not release pause");
            bool rejected = false;
            try { using var foreign = new ObserverLease(root, "CampusTerminal-wrong"); }
            catch (InvalidOperationException) { rejected = true; }
            check(rejected && File.ReadAllText(path) == "CampusTerminal-existing", "Foreign marker cannot be adopted or overwritten");
        }
        finally { Directory.Delete(root, true); }
    }
}
