// SPDX-License-Identifier: GPL-3.0-or-later
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using System.Collections.Concurrent;
using CampusAuth;

internal static class LoggingChecks
{
    internal static void Run(Action<bool, string> check)
    {
        long freq = System.Diagnostics.Stopwatch.Frequency;
        bool WaitStage(ConcurrentQueue<string> events, string stage) => SpinWait.SpinUntil(() => events.Contains(stage), TimeSpan.FromSeconds(2));
        void Poll(RuntimeDiagnostics detector, long start, long end)
        {
            for (long tick = start + freq; tick < end; tick += freq) detector.Observe(tick);
            detector.Observe(end);
        }
        {
            var events = new ConcurrentQueue<string>(); using var detector = new RuntimeDiagnostics((stage, _) => events.Enqueue(stage));
            detector.StartSession(freq); Poll(detector, freq, 32 * freq);
            check(WaitStage(events, "SessionProgressStalled") && events.SequenceEqual(new[] { "SessionProgressStalled" }),
                "Independent detector reports a session loop stall without another stage event");
            detector.PulseSession(33 * freq);
            check(WaitStage(events, "SessionProgressRecovered") && events.Last() == "SessionProgressRecovered",
                "Session loop recovery is recorded on the first fresh pulse");
        }
        {
            var events = new ConcurrentQueue<string>(); string? recordedCorrelation = null;
            using var detector = new RuntimeDiagnostics((stage, detail) =>
            {
                events.Enqueue(stage);
                if (stage == "HostRequestStalled") Interlocked.Exchange(ref recordedCorrelation,
                    detail.GetType().GetProperty("diagnosticRequestId")?.GetValue(detail) as string);
            });
            detector.StartRequest(42, "status", "trace-42", 40 * freq); Poll(detector, 40 * freq, 61 * freq);
            check(WaitStage(events, "HostRequestStalled") && Volatile.Read(ref recordedCorrelation) == "trace-42",
                "Request execution stall preserves validated correlation alongside elapsed time");
            detector.EndRequest(62 * freq);
            check(WaitStage(events, "HostRequestRecovered") && events.Last() == "HostRequestRecovered",
                "Request completion records recovery and safe correlation metadata");
        }
        {
            var events = new ConcurrentQueue<string>(); using var detector = new RuntimeDiagnostics((stage, _) => events.Enqueue(stage));
            detector.StartHeartbeat(70 * freq); Poll(detector, 70 * freq, 86 * freq);
            check(WaitStage(events, "HeartbeatCycleStalled") && events.Last() == "HeartbeatCycleStalled",
                "Heartbeat cycle hang is detected independently");
            detector.EndHeartbeat(87 * freq);
            check(WaitStage(events, "HeartbeatCycleRecovered") && events.Last() == "HeartbeatCycleRecovered",
                "Heartbeat cycle recovery is recorded");
        }
        {
            var events = new ConcurrentQueue<string>(); using var detector = new RuntimeDiagnostics((stage, _) => events.Enqueue(stage));
            detector.StartSession(100 * freq); Poll(detector, 100 * freq, 105 * freq);
            int beforeSuspendGap = events.Count;
            detector.Observe(126 * freq); // A scheduler gap is treated as suspend/observation loss.
            Poll(detector, 126 * freq, 145 * freq);
            check(events.Count == beforeSuspendGap, "A long scheduler or suspend gap does not create a false stall");
            Poll(detector, 145 * freq, 158 * freq);
            check(WaitStage(events, "SessionProgressStalled") && events.Last() == "SessionProgressStalled",
                "A genuine stall after the suspend grace is still detected");
        }

        using (var emitEntered = new ManualResetEventSlim())
        using (var releaseEmit = new ManualResetEventSlim())
        {
            var blockedWriter = new RuntimeDiagnostics((stage, _) =>
            {
                if (stage == "SessionProgressStalled") { emitEntered.Set(); releaseEmit.Wait(); }
            });
            blockedWriter.StartSession(freq);
            for (long tick = freq + freq; tick <= 32 * freq; tick += freq) blockedWriter.Observe(tick);
            check(emitEntered.Wait(TimeSpan.FromSeconds(2)), "Diagnostics writer begins the deliberately blocked emission");
            var pulse = Task.Run(() => blockedWriter.PulseSession(33 * freq));
            check(pulse.Wait(TimeSpan.FromMilliseconds(500)), "Session progress pulse does not wait for a blocked journal emitter");
            releaseEmit.Set();
            blockedWriter.Dispose();
        }

        using (var entered = new ManualResetEventSlim())
        using (var release = new ManualResetEventSlim())
        {
            var detector = new RuntimeDiagnostics((_, _) => { entered.Set(); release.Wait(); });
            try
            {
                detector.StartSession(freq);
                Poll(detector, freq, 32 * freq);
                check(entered.Wait(TimeSpan.FromSeconds(2)), "Blocked sink fixture receives a diagnostic event");
                detector.Dispose(); // Writer still owns the wait handle after this bounded join.
                release.Set();
                check(SpinWait.SpinUntil(() => detector.IsStopped, TimeSpan.FromSeconds(2)),
                    "A writer stalled during disposal exits safely after its sink resumes");
            }
            finally { release.Set(); detector.Dispose(); }
        }

        string root = Path.Combine(Path.GetTempPath(), "campus-logging-checks-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            var today = new DateTime(2026, 10, 8, 12, 0, 0, DateTimeKind.Utc);
            var journalDir = Path.Combine(root, "journal");
            var journal = new RuntimeJournal(journalDir, 1, () => today);
            for (int i = 0; i < 4; i++) journal.Write("TwoCampusRoundsPassed", new { ordinal = i });
            var segments = Directory.GetFiles(journalDir, "events-*.jsonl").Order().ToArray();
            check(segments.Length == 4, "Repeated journal rollover keeps each segment immutable and uniquely numbered");
            var rows = segments.SelectMany(file => File.ReadAllLines(file)).Select(line => JsonDocument.Parse(line))
                .Select(doc => (Sequence: doc.RootElement.GetProperty("sequence").GetInt64(),
                    Run: doc.RootElement.GetProperty("run").GetString(), Pid: doc.RootElement.GetProperty("pid").GetInt32())).ToArray();
            check(rows.Select(row => row.Sequence).SequenceEqual(new long[] { 1, 2, 3, 4 }), "Journal sequence is monotonic across segments");
            check(rows.All(row => row.Run == journal.RunId && row.Pid == Environment.ProcessId), "Journal rows identify run and process");
            File.WriteAllText(Path.Combine(journalDir, "events-20260901.jsonl.previous"),
                "{\"at\":\"2026-10-08T10:00:00+00:00\",\"stage\":\"TwoCampusRoundsPassed\"}\n");
            check(journal.RecentRecoveryEvents(10).Length == 5, "Recovery reader includes legacy previous files and numbered segments");
            var newest = journal.RecentRecoveryEvents(1)[0];
            string newestTime = (string)newest.GetType().GetProperty("time")!.GetValue(newest)!;
            check(newestTime == today.ToLocalTime().ToString("HH:mm:ss"), "Recent recovery reader sorts active and legacy rows by actual timestamp");
            File.WriteAllText(Path.Combine(journalDir, "events-20260801-0001.jsonl"), "old");
            File.WriteAllText(Path.Combine(journalDir, "events-20260908-0001.jsonl"), "kept");
            journal.Write("RetentionCheck");
            check(!File.Exists(Path.Combine(journalDir, "events-20260801-0001.jsonl")) &&
                File.Exists(Path.Combine(journalDir, "events-20260908-0001.jsonl")), "Retention prunes by UTC calendar day, not segment count");

            string archiveDir = Path.Combine(root, "archive-journal");
            Directory.CreateDirectory(archiveDir);
            string shortArchive = Path.Combine(archiveDir, "events-20261008-0001.jsonl");
            File.WriteAllText(shortArchive, "short-archive-must-stay-unchanged");
            var archiveJournal = new RuntimeJournal(archiveDir, 1, () => today);
            archiveJournal.Write("before-rollover");
            archiveJournal.Write("after-rollover");
            check(File.ReadAllText(shortArchive) == "short-archive-must-stay-unchanged" &&
                File.Exists(Path.Combine(archiveDir, "events-20261008-0002.jsonl")),
                "Short existing numbered archives remain immutable and rollover chooses the first unused number");

            string eventFailDir = Path.Combine(root, "event-error");
            Directory.CreateDirectory(eventFailDir);
            Directory.CreateDirectory(Path.Combine(eventFailDir, "events-20261008.jsonl"));
            var eventFail = new RuntimeJournal(eventFailDir, 1024, () => today);
            eventFail.Write("will-fail");
            eventFail.Heartbeat(new { phase = "test" });
            check(eventFail.EventError == "RuntimeLogUnavailable" && eventFail.HeartbeatError == null,
                "Heartbeat success does not clear a failed event-writer status");
            string heartbeatFailDir = Path.Combine(root, "heartbeat-error");
            Directory.CreateDirectory(heartbeatFailDir);
            Directory.CreateDirectory(Path.Combine(heartbeatFailDir, "heartbeat.json"));
            var heartbeatFail = new RuntimeJournal(heartbeatFailDir, 1024, () => today);
            heartbeatFail.Write("event-ok"); heartbeatFail.Heartbeat(new { phase = "test" }); heartbeatFail.Write("event-ok-again");
            check(heartbeatFail.EventError == null && heartbeatFail.HeartbeatError == "HeartbeatLogUnavailable",
                "Event success does not clear a failed heartbeat-writer status");

            string history = Path.Combine(root, "history.json");
            RecoveryLog.UseStore(history);
            check(!RecoveryLog.BeginCampaign(null) && RecoveryLog.Recent().Length == 0, "Normal connection without campaign metadata adds no history");
            for (int i = 0; i < 105; i++)
            {
                string id = "campaign-" + i;
                RecoveryLog.BeginCampaign(id);
                RecoveryLog.Observe(0, "AuthenticationGenerationStarted");
                RecoveryLog.Observe(0, "TwoCampusRoundsPassed");
                RecoveryLog.EndCampaign();
            }
            check(RecoveryLog.Recent().Length == 100, "Recovery history retains the newest 100 entries");
            check(RecoveryLog.Recent()[0]["campaignId"]!.GetValue<string>() == "campaign-5", "History capacity removes only the oldest entries");
            RecoveryLog.BeginCampaign("campaign-104");
            check(RecoveryLog.Recent().Length == 100 && RecoveryLog.Recent()[^1]["result"]!.GetValue<string>() == "重连中",
                "A repeated outer attempt reopens its existing campaign instead of duplicating a history row");
            RecoveryLog.UseStore(history);
            check(RecoveryLog.Recent().Length == 100, "One hundred history entries reload from disk");

            string corrupt = Path.Combine(root, "corrupt.json");
            File.WriteAllText(corrupt, "{broken");
            bool diagnosed = false;
            using var diagnosisArrived = new ManualResetEventSlim();
            RecoveryLog.UseStore(corrupt, _ => { diagnosed = true; diagnosisArrived.Set(); });
            diagnosisArrived.Wait(TimeSpan.FromSeconds(2));
            check(diagnosed && File.Exists(corrupt) && Directory.GetFiles(root, "corrupt.json.corrupt-*").Length == 1,
                "Corrupt history is preserved, quarantined, and diagnosed");

            string quarantineRetry = Path.Combine(root, "retry-corrupt.json");
            const string corruptText = "{bad-source";
            File.WriteAllText(quarantineRetry, corruptText);
            RecoveryLog.QuarantineFailureForTests = _ => true;
            RecoveryLog.UseStore(quarantineRetry);
            RecoveryLog.BeginCampaign("blocked-write");
            check(RecoveryLog.Error == "RecoveryLogUnavailable" && File.ReadAllText(quarantineRetry) == corruptText &&
                Directory.GetFiles(root, "retry-corrupt.json.corrupt-*").Length == 0,
                "Failed quarantine keeps writes blocked and leaves the corrupt source untouched");
            RecoveryLog.QuarantineFailureForTests = _ => false;
            RecoveryLog.BeginCampaign("retry-quarantine");
            string quarantinePath = Directory.GetFiles(root, "retry-corrupt.json.corrupt-*").SingleOrDefault() ?? "";
            check(quarantinePath != "" && File.ReadAllText(quarantinePath) == corruptText &&
                JsonNode.Parse(File.ReadAllText(quarantineRetry)) is JsonArray && Directory.GetFiles(root, "retry-corrupt.json.corrupt-*").Length == 1,
                "A later unique quarantine succeeds before any replacement of the corrupt source");
            RecoveryLog.QuarantineFailureForTests = null;

            string internalStore = Path.Combine(root, "internal-history.json");
            RecoveryLog.UseStore(internalStore);
            RecoveryLog.Observe(0, "AuthenticationGenerationStarted");
            RecoveryLog.Observe(0, "TwoCampusRoundsPassed");
            check(RecoveryLog.Recent().Length == 0, "Initial generation-zero session remains excluded");
            RecoveryLog.Observe(1, "AuthenticationGenerationStarted");
            RecoveryLog.Observe(1, "TwoCampusRoundsPassed");
            RecoveryLog.Observe(2, "AuthenticationGenerationStarted");
            RecoveryLog.Observe(2, "TwoCampusRoundsPassed");
            check(RecoveryLog.Recent().Length == 2 && RecoveryLog.Recent().All(row => row["result"]!.GetValue<string>() == "成功"),
                "Two ordinary-session internal recovery generations create two completed rows");
            RecoveryLog.UseStore(Path.Combine(root, "outer-history.json"));
            RecoveryLog.BeginCampaign("outer-01");
            RecoveryLog.Observe(0, "AuthenticationGenerationStarted");
            RecoveryLog.Observe(1, "AuthenticationGenerationStarted");
            RecoveryLog.Observe(1, "TwoCampusRoundsPassed");
            check(RecoveryLog.Recent().Length == 1 && RecoveryLog.Recent()[0]["result"]!.GetValue<string>() == "成功",
                "Outer automatic campaign internal retries complete one pending row without duplicates");

            string blockedStore = Path.Combine(root, "store-is-a-directory");
            Directory.CreateDirectory(blockedStore);
            bool writeDiagnosed = false;
            using var writeDiagnosisArrived = new ManualResetEventSlim();
            RecoveryLog.UseStore(blockedStore, _ => { writeDiagnosed = true; writeDiagnosisArrived.Set(); });
            RecoveryLog.BeginCampaign("atomic-failure");
            writeDiagnosisArrived.Wait(TimeSpan.FromSeconds(2));
            check(writeDiagnosed && RecoveryLog.Error == "RecoveryLogUnavailable" && !File.Exists(blockedStore + ".tmp"),
                "Atomic history write failure is observable, diagnosed, and temporary files are cleaned");
        }
        finally { Directory.Delete(root, true); }
    }
}
