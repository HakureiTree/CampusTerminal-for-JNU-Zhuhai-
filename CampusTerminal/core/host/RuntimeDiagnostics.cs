// SPDX-License-Identifier: GPL-3.0-or-later
using System.Collections.Concurrent;
using System.Diagnostics;

namespace CampusAuth;

// A dedicated writer keeps slow journal I/O away from the session loop and detector lock.
internal sealed class RuntimeDiagnostics : IDisposable
{
    private readonly object sync = new();
    private readonly Action<string, object> emit;
    private readonly ConcurrentQueue<(string Stage, object Detail)> pending = new();
    private readonly AutoResetEvent signal = new(false);
    private readonly Thread writer;
    private long lastPoll, requestSince, sessionSince, heartbeatSince, heartbeatCompleted;
    private int requestStalled, sessionStalled, heartbeatStalled, requestId, disposed;
    private string requestMethod = "unknown";
    private string? diagnosticRequestId;

    internal RuntimeDiagnostics(Action<string, object> emit)
    {
        this.emit = emit;
        writer = new Thread(WriteEvents) { IsBackground = true, Name = "BackendDiagnosticWriter" };
        writer.Start();
    }

    internal void StartRequest(int id, string method, string? correlationId, long now)
    { lock (sync) { if (disposed != 0) return; requestId = id; requestMethod = method; diagnosticRequestId = correlationId; requestSince = now; requestStalled = 0; } }
    internal void EndRequest(long now)
    {
        (string, object)? row = null;
        lock (sync)
        {
            if (disposed != 0) return;
            if (requestStalled != 0) row = ("HostRequestRecovered", new { id = requestId, diagnosticRequestId, method = requestMethod,
                durationMs = (long)Stopwatch.GetElapsedTime(requestSince, now).TotalMilliseconds });
            requestSince = 0; requestStalled = 0;
        }
        Publish(row);
    }
    internal void StartSession(long now) { lock (sync) { if (disposed == 0) { sessionSince = now; sessionStalled = 0; } } }
    internal void PulseSession(long now)
    {
        (string, object)? row = null;
        lock (sync)
        {
            if (disposed != 0) return;
            if (sessionStalled != 0) row = ("SessionProgressRecovered", new {
                durationMs = (long)Stopwatch.GetElapsedTime(sessionSince, now).TotalMilliseconds });
            sessionSince = now; sessionStalled = 0;
        }
        Publish(row);
    }
    internal void StopSession() { lock (sync) { sessionSince = 0; sessionStalled = 0; } }
    internal void StartHeartbeat(long now) { lock (sync) { if (disposed == 0) heartbeatSince = now; } }
    internal void EndHeartbeat(long now)
    {
        (string, object)? row = null;
        lock (sync)
        {
            if (disposed != 0) return;
            if (heartbeatStalled != 0) row = ("HeartbeatCycleRecovered", new { durationMs = heartbeatSince == 0 ? 0 : (long)Stopwatch.GetElapsedTime(heartbeatSince, now).TotalMilliseconds });
            heartbeatSince = 0; heartbeatCompleted = now; heartbeatStalled = 0;
        }
        Publish(row);
    }

    internal void Observe(long now)
    {
        List<(string Stage, object Detail)> rows = new();
        lock (sync)
        {
            if (disposed != 0) return;
            if (lastPoll != 0 && Stopwatch.GetElapsedTime(lastPoll, now) > TimeSpan.FromSeconds(10))
            {
                if (requestSince != 0) requestSince = now;
                if (sessionSince != 0) sessionSince = now;
                if (heartbeatSince != 0) heartbeatSince = now;
                if (heartbeatCompleted != 0) heartbeatCompleted = now;
                lastPoll = now;
                return;
            }
            lastPoll = now;
            if (requestSince != 0 && requestStalled == 0 && Stopwatch.GetElapsedTime(requestSince, now) > TimeSpan.FromSeconds(20))
            {
                requestStalled = 1;
                rows.Add(("HostRequestStalled", new { id = requestId, diagnosticRequestId, method = requestMethod, thresholdSeconds = 20 }));
            }
            if (sessionSince != 0 && sessionStalled == 0 && Stopwatch.GetElapsedTime(sessionSince, now) > TimeSpan.FromSeconds(30))
            {
                sessionStalled = 1;
                rows.Add(("SessionProgressStalled", new { thresholdSeconds = 30 }));
            }
            bool heartbeatLate = heartbeatSince != 0
                ? Stopwatch.GetElapsedTime(heartbeatSince, now) > TimeSpan.FromSeconds(15)
                : heartbeatCompleted != 0 && Stopwatch.GetElapsedTime(heartbeatCompleted, now) > TimeSpan.FromSeconds(15);
            if (heartbeatLate && heartbeatStalled == 0)
            {
                heartbeatStalled = 1;
                rows.Add(("HeartbeatCycleStalled", new { thresholdSeconds = 15 }));
            }
        }
        foreach (var row in rows) Publish(row);
    }

    private void Publish((string Stage, object Detail)? row)
    {
        if (row is not { } value) return;
        lock (sync)
        {
            if (disposed != 0) return;
            pending.Enqueue(value);
            signal.Set();
        }
    }

    private void WriteEvents()
    {
        try
        {
            while (Volatile.Read(ref disposed) == 0 || !pending.IsEmpty)
            {
                while (pending.TryDequeue(out var row))
                {
                    try { emit(row.Stage, row.Detail); }
                    catch (Exception) { /* Diagnostics must never take down session or watchdog threads. */ }
                }
                signal.WaitOne(250);
            }
        }
        finally { signal.Dispose(); }
    }

    internal bool IsStopped => !writer.IsAlive;

    public void Dispose()
    {
        lock (sync)
        {
            if (disposed != 0) return;
            disposed = 1;
            signal.Set();
        }
        writer.Join(TimeSpan.FromSeconds(2));
        // The writer owns its signal: a stalled sink may outlive the bounded join.
    }
}
