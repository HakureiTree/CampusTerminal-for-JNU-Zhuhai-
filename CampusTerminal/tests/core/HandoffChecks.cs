// SPDX-License-Identifier: GPL-3.0-or-later
using CampusAuth;

internal static class HandoffChecks
{
    internal static void Run(Action<bool, string> check)
    {
        foreach (var trigger in Enum.GetValues<HandoffTrigger>())
            check(!OriginalHandoff.Required(false, trigger, true), "Disabled fallback never hands back");
        check(!OriginalHandoff.Required(true, HandoffTrigger.ManualDisconnect, true), "Manual disconnect stays disconnected");
        check(OriginalHandoff.Required(true, HandoffTrigger.ApplicationExit, false), "Enabled exit hands back");
        check(!OriginalHandoff.Required(true, HandoffTrigger.RuntimeFailure, false), "Pre-auth failure does not launch original");
        check(OriginalHandoff.Required(true, HandoffTrigger.RuntimeFailure, true), "Runtime failure hands back");
        var ops = new Operations();
        var controller = new OriginalHandoff(ops, _ => {});
        check(controller.Run().Succeeded && ops.Starts == 1 && ops.Resumed, "Successful handoff");
        check(!controller.Run().Succeeded && ops.Starts == 1, "Handoff cannot repeat");
        ops = new Operations { Existing = true };
        check(new OriginalHandoff(ops, _ => {}).Run().Succeeded && ops.Starts == 0, "Existing correct instance not duplicated");
        ops = new Operations { StartSucceedsAt = 2 };
        check(new OriginalHandoff(ops, _ => {}).Run().Succeeded && ops.Starts == 2, "One supplemental start");
        ops = new Operations { StartSucceedsAt = 2, ThrowFirstLaunch = true };
        check(new OriginalHandoff(ops, _ => {}).Run().Succeeded && ops.Starts == 2, "Launch request error receives one supplemental start");
        ops = new Operations { StartSucceedsAt = 3 };
        check(!new OriginalHandoff(ops, _ => {}).Run().Succeeded && ops.Starts == 2 && !ops.Resumed, "Start failure bounded");
        foreach (string failure in new[] { "preflight", "stopped", "pause", "service", "authentication", "network", "monitor" })
        {
            ops = new Operations { Failure = failure };
            var result = new OriginalHandoff(ops, _ => {}).Run();
            check(!result.Succeeded && result.Error == failure && !ops.Resumed, "Failure preserves pause: " + failure);
            if (failure is "preflight" or "stopped" or "pause")
                check(ops.Starts == 0 && !ops.ServiceRestored, "Safety gate precedes original actions");
        }
    }

    private sealed class Operations : IOriginalHandoffOperations
    {
        public string? Failure;
        public bool Existing, Resumed, ServiceRestored, ThrowFirstLaunch;
        public int Starts, StartSucceedsAt = 1;
        private void Verify(string step) { if (Failure == step) throw new InvalidOperationException(step); }
        public void Preflight() => Verify("preflight");
        public void ConfirmReplacementStopped() => Verify("stopped");
        public void ConfirmPauseOwned() => Verify("pause");
        public void RestoreOriginalService() { Verify("service"); ServiceRestored = true; }
        public bool CorrectOriginalInstanceExists() => Existing;
        public void StartOriginalNormally()
        {
            Starts++;
            if (ThrowFirstLaunch && Starts == 1) throw new InvalidOperationException("OriginalLaunchRequestFailed");
        }
        public bool WaitForOriginalStart() => Starts >= StartSucceedsAt;
        public void VerifyOriginalAuthentication() => Verify("authentication");
        public void VerifyTwoCampusRoundsAndDefaultPath() => Verify("network");
        public void ResumeAndVerifyOriginalMonitor() { Verify("monitor"); Resumed = true; }
    }
}
