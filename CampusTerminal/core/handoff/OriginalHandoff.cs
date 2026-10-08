// SPDX-License-Identifier: GPL-3.0-or-later
namespace CampusAuth;

internal enum HandoffTrigger { RuntimeFailure, ApplicationExit, ManualDisconnect }
internal sealed record HandoffResult(bool Succeeded, string Stage, string? Error);

internal interface IOriginalHandoffOperations
{
    void Preflight();
    void ConfirmReplacementStopped();
    void ConfirmPauseOwned();
    void RestoreOriginalService();
    bool CorrectOriginalInstanceExists();
    void StartOriginalNormally();
    bool WaitForOriginalStart();
    void VerifyOriginalAuthentication();
    void VerifyTwoCampusRoundsAndDefaultPath();
    void ResumeAndVerifyOriginalMonitor();
}

internal sealed class OriginalHandoff(IOriginalHandoffOperations operations, Action<string> note)
{
    private int started;

    internal static bool Required(bool enabled, HandoffTrigger trigger, bool sessionWasStarted) =>
        enabled && (trigger == HandoffTrigger.ApplicationExit ||
                    trigger == HandoffTrigger.RuntimeFailure && sessionWasStarted);

    internal HandoffResult Run()
    {
        if (Interlocked.Exchange(ref started, 1) != 0)
            return new(false, "Blocked", "HandoffAlreadyAttempted");
        string stage = "Preflight";
        void Step(string name, Action operation)
        {
            stage = name;
            note(name);
            operation();
        }
        try
        {
            Step("Preflight", operations.Preflight);
            Step("ReplacementStopped", operations.ConfirmReplacementStopped);
            Step("PauseOwned", operations.ConfirmPauseOwned);
            Step("RestoreOriginalService", operations.RestoreOriginalService);
            Step("StartOriginalNormally", () =>
            {
                // Service startup may already have launched the correct client.
                for (int attempt = 0; attempt < 2; attempt++)
                {
                    if (operations.CorrectOriginalInstanceExists()) return;
                    operations.ConfirmPauseOwned();
                    try { operations.StartOriginalNormally(); }
                    catch (InvalidOperationException ex) when (ex.Message == "OriginalLaunchRequestFailed") { }
                    if (operations.WaitForOriginalStart()) return;
                }
                throw new InvalidOperationException("OriginalStartFailed");
            });
            Step("VerifyOriginalAuthentication", operations.VerifyOriginalAuthentication);
            Step("VerifyOriginalNetwork", operations.VerifyTwoCampusRoundsAndDefaultPath);
            Step("ResumeOriginalMonitor", operations.ResumeAndVerifyOriginalMonitor);
            return new(true, "Complete", null);
        }
        catch (Exception ex)
        {
            // No monitor resume after failure; leave the owned pause for diagnosis.
            return new(false, stage, ex is InvalidOperationException ? ex.Message : ex.GetType().Name);
        }
    }
}
