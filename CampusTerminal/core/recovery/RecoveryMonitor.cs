// SPDX-License-Identifier: GPL-3.0-or-later
namespace CampusAuth;

internal interface ISessionMonitor : IDisposable
{
    bool Verified { get; }
    bool Held { get; }
    string? Tick(TimeSpan now);
}

// One monitor belongs to exactly one authentication generation. Disposing it
// cancels and joins its probes before another generation can begin.
internal sealed class RecoveryMonitor(ITrafficSampler sampler, IRecoveryProbe probe,
    string address, Action<string> log, bool requireVerification = false,
    RecoverySettings? settings = null, Action<TrafficSample, double, double>? telemetry = null,
    Func<bool>? recoveryEnabled = null) : ISessionMonitor
{
    private readonly RecoverySettings options = settings ?? new();
    private readonly TrafficDropDetector detector = new((settings ?? new()).BaselineSamples,
        (settings ?? new()).LowSamples, (settings ?? new()).DropFraction, (settings ?? new()).MinimumBytesPerSecond);
    private readonly CancellationTokenSource cancellation = new();
    private Task<RecoveryEvidence>? pending;
    private TimeSpan nextSample;
    private TimeSpan nextCheck;
    private TimeSpan probeStarted;
    private TimeSpan? degradedSince;
    public bool Verified { get; private set; }
    public bool Held { get; private set; }

    public string? Tick(TimeSpan now)
    {
        if (pending != null)
        {
            if (!pending.IsCompleted)
                return now - probeStarted > TimeSpan.FromSeconds(20) && !Held && !Verified ? "RecoveryProbeTimeout" : null;
            RecoveryEvidence result;
            try { result = pending.GetAwaiter().GetResult(); }
            catch (Exception ex) when (ex is OperationCanceledException or System.Net.Sockets.SocketException or System.Net.Http.HttpRequestException)
            { result = new(false, false, "ProbeIndeterminate"); }
            pending = null;
            log(result.Reason);
            LogEvidence(result);
            if (result.Verified)
            {
                requireVerification = false;
                Verified = Held = true;
                degradedSince = null;
            }
            else if (result.Unavailable)
            {
                if (requireVerification) return "RecoveryVerificationFailed";
                requireVerification = false;
                if (recoveryEnabled?.Invoke() ?? true) return "RecoveryRequested";
                Held = true;
                degradedSince ??= now;
            }
            else
            {
                // DNS/partial/indeterminate: keep the EAP session and keep probing.
                requireVerification = false;
                Held = true;
                degradedSince ??= now;
            }
            detector.Reset();
            nextCheck = now + TimeSpan.FromSeconds(options.HealthCheckSeconds);
        }
        if (now < nextSample) return null;
        nextSample = now + TimeSpan.FromSeconds(1);
        bool dropped;
        try
        {
            var sample = sampler.Read(now);
            dropped = detector.Observe(sample);
            telemetry?.Invoke(sample, detector.Rate, detector.Baseline);
        }
        catch (Exception ex) when (ex is System.Net.NetworkInformation.NetworkInformationException or InvalidOperationException)
        { return "TrafficSamplerUnavailable"; }
        if (pending == null && (dropped || now >= nextCheck))
        {
            log(dropped ? "AbnormalTrafficDrop" : "CampusHealthCheck");
            probeStarted = now;
            pending = probe.CheckAsync(address, cancellation.Token);
        }
        return null;
    }

    public void Dispose()
    {
        cancellation.Cancel();
        try
        {
            if (pending is { IsCompletedSuccessfully: true })
                LogEvidence(pending.GetAwaiter().GetResult());
            else log("ProbeCancelledAtAttemptBoundary");
        }
        catch (Exception) { log("ProbeCancelledAtAttemptBoundary"); }
        finally { cancellation.Dispose(); pending = null; }
    }

    private void LogEvidence(RecoveryEvidence result) =>
        log("ProbeEvidence:" + System.Text.Json.JsonSerializer.Serialize(result,
            new System.Text.Json.JsonSerializerOptions { Converters = { new System.Text.Json.Serialization.JsonStringEnumConverter() } }));
}
