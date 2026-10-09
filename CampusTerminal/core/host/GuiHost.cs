// SPDX-License-Identifier: GPL-3.0-or-later
using System.Diagnostics;
using System.Net;
using System.Security.Cryptography;
using System.Text.Json.Nodes;

namespace CampusAuth;

internal static class GuiHost
{
    private static readonly object Gate = new();
    private static string phase = "idle";
    private static string? error;
    private static string? firstError;
    private static bool acceptanceActive;
    private static int heartbeatCount;
    private static CancellationTokenSource? session;
    private static Task? sessionTask;
    private static bool autoReconnect = true;
    private static bool inodeFallback;
    private static bool handoffAttempted;
    private static bool handoffRunning;
    private static string? handoffReport;
    private static JsonNode? probeEvidence;
    private static HandoffTrigger stopIntent = HandoffTrigger.RuntimeFailure;
    private static CancellationTokenSource? lifetime;
    private static int generation;
    private static RuntimeJournal? journal;
    private static int attempt;
    private static bool attemptsExhausted;
    private static int heartbeatTicks;
    private static DateTime lastGuiLaunch = DateTime.MinValue;
    private static int guiLaunchFails;
    private static bool allowGuiResident = true;
    private static int connectSerial;
    private static int countedSerial = -1;
    private static RuntimeDiagnostics? diagnostics;
    private static int heartbeatRunning;

    public static int Run()
    {
        using var ownership = new Mutex(true, "Local\\CampusTerminal.GuiHost", out var acquired);
        if (!acquired) return 0;
        using var stop = new CancellationTokenSource();
        lifetime = stop;
        journal = new RuntimeJournal(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
            "CampusTerminal", "logs"));
        diagnostics = new RuntimeDiagnostics((stage, detail) => journal.Write(stage, detail));
        AutoFailureBudget.ResetOnStart();
        journal.Write("BackendStarted", new { version = "CampusTerminal-1.3.19" });
        RecoveryLog.UseStore(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
            "CampusTerminal", "recovery-events.json"), diagnosis => journal.Write("RecoveryLogError", new { diagnosis }));
        UnhandledExceptionEventHandler fatalHandler = (_, e) =>
        {
            var ex = e.ExceptionObject as Exception;
            journal.Write("BackendUnhandledException", SafeException(ex));
            journal.Write("BackendCrashed");
        };
        AppDomain.CurrentDomain.UnhandledException += fatalHandler;
        AllowOwnFirewall();
        RegisterHostTask();
        RetireDuplicateAutostart();
        TetherBinding.Start(stop.Token);
        CampusRoute.RecoverStale(id => Adapters.PhonePath(id) || Adapters.AlternativePath(id));
        using var watchdogStop = new CancellationTokenSource();
        var watchdog = new Thread(() => Watchdog(watchdogStop.Token)) { IsBackground = true, Name = "BackendDiagnosticsWatchdog" };
        watchdog.Start();
        using var heartbeat = new Timer(_ =>
        {
            if (stop.IsCancellationRequested) return;
            if (Interlocked.CompareExchange(ref heartbeatRunning, 1, 0) != 0) return;
            diagnostics.StartHeartbeat(Stopwatch.GetTimestamp());
            try
            {
                journal.Heartbeat(SafeHeartbeatStatus());
                NotePaths(false);
                MaintainCampusRoute();
                EnsureGuiResident();
            }
            catch (Exception ex) { journal.Write("HeartbeatCallbackError", SafeException(ex)); }
            finally
            {
                diagnostics.EndHeartbeat(Stopwatch.GetTimestamp());
                Volatile.Write(ref heartbeatRunning, 0);
            }
        }, null, 0, 5000);
        ConsoleCancelEventHandler cancel = (_, e) => { e.Cancel = true; stop.Cancel(); };
        Console.CancelKeyPress += cancel;
        try { IpcServer.Listen(Handle, stop.Token); }
        finally
        {
            StopSession();
            heartbeat.Dispose();
            watchdogStop.Cancel();
            watchdog.Join(TimeSpan.FromSeconds(2));
            diagnostics.Dispose();
            Task? remaining;
            lock (Gate) remaining = sessionTask;
            if (remaining != null && !remaining.Wait(TimeSpan.FromSeconds(8)))
                journal.Write("ShutdownSessionWaitTimeout", new { thresholdSeconds = 8 });
            CampusRoute.RestoreAll();
            journal.Write("BackendStopped");
            AppDomain.CurrentDomain.UnhandledException -= fatalHandler;
            Console.CancelKeyPress -= cancel;
            lifetime = null;
            ownership.ReleaseMutex();
        }
        return 0;
    }

    private static object Handle(JsonObject request)
    {
        var method = request["method"]?.GetValue<string>() ?? "";
        var id = request["id"]?.GetValue<int>() ?? 0;
        string? correlationId = SafeRequestCorrelation(request);
        long started = Stopwatch.GetTimestamp();
        diagnostics?.StartRequest(id, SafeMethod(method), correlationId, started);
        string outcome = "ok";
        try
        {
            var reply = HandleCore(id, method, request);
            if (reply.GetType().GetProperty("ok")?.GetValue(reply) is bool ok && !ok) outcome = "error";
            return reply;
        }
        catch (Exception ex)
        {
            outcome = "error";
            journal?.Write("HostRequestError", new { id, diagnosticRequestId = correlationId, method = SafeMethod(method), exception = SafeException(ex) });
            throw;
        }
        finally
        {
            long duration = (long)Stopwatch.GetElapsedTime(started).TotalMilliseconds;
            journal?.Write("HostRequestCompleted", new { id, diagnosticRequestId = correlationId, method = SafeMethod(method), durationMs = duration, outcome });
            diagnostics?.EndRequest(Stopwatch.GetTimestamp());
        }
    }

    private static object HandleCore(int id, string method, JsonObject request) => method switch
        {
            "status" => Status(id),
            "listAdapters" => new { ok = true, id, adapters = Adapters.List() },
            "connect" => Connect(id, request),
            "configure" => Configure(id, request),
            "disconnect" => Disconnect(id, false),
            "releaseCampus" => ReleaseCampus(id, request),
            "shutdown" => Shutdown(id, request),
            _ => new { ok = false, id, error = "UnknownMethod" }
        };

    private static string SafeMethod(string method) => method is "status" or "listAdapters" or "connect" or "configure" or "disconnect" or "releaseCampus" or "shutdown" ? method : "unknown";

    private static string? SafeRequestCorrelation(JsonObject request)
    {
        if (request["diagnosticRequestId"] is not System.Text.Json.Nodes.JsonValue value || !value.TryGetValue<string>(out var id) ||
            string.IsNullOrEmpty(id) || id.Length > 64 || id.Any(character => !char.IsAsciiLetterOrDigit(character) && character is not ('.' or '_' or '-')))
            return null;
        return id;
    }

    private static object SafeException(Exception? ex)
    {
        if (ex == null) return new { errorType = "UnknownException" };
        var frames = new System.Diagnostics.StackTrace(ex, false).GetFrames()?.Take(4).Select(frame => new
        {
            function = Bounded(frame.GetMethod()?.Name, 128), file = Bounded(Path.GetFileName(frame.GetFileName() ?? ""), 128),
            line = Math.Max(0, frame.GetFileLineNumber())
        }).ToArray() ?? [];
        return new { errorType = Bounded(ex.GetType().Name, 128), frames };
    }

    private static string Bounded(string? value, int max) => string.IsNullOrEmpty(value) ? "unknown" : value[..Math.Min(value.Length, max)];

    private static void Watchdog(CancellationToken token)
    {
        while (!token.IsCancellationRequested)
        {
            Thread.Sleep(1000);
            if (token.IsCancellationRequested) break;
            diagnostics?.Observe(Stopwatch.GetTimestamp());
        }
    }

    private static object Status(int id)
    {
        lock (Gate)
            return new { ok = true, id, version = "CampusTerminal-1.3.19", processId = Environment.ProcessId,
                alternative = Adapters.AlternativePath(Guid.Empty),
                executable = Environment.ProcessPath,
                phase, error, firstError, acceptanceActive, heartbeatCount,
                elevated = LiveGate.Elevated(), active = session != null, generation,
                options = new { autoReconnect, inodeFallback }, handoff = new { attempted = handoffAttempted, running = handoffRunning, report = handoffReport },
                logging = new { directory = journal?.DirectoryPath, error = journal?.Error, eventError = journal?.EventError,
                    heartbeatError = journal?.HeartbeatError, recoveryError = RecoveryLog.Error },
                capabilities = new { normal = true, fast = false, sso = false, featureSpoofing = false },
                recovery = new { enabled = autoReconnect, attempt, maxAttempts = ConnectionRetryPolicy.MaxAttempts,
                    timeoutSeconds = ConnectionRetryPolicy.AttemptTimeout.TotalSeconds,
                    exhausted = attemptsExhausted || AutoFailureBudget.Blocked, autoFailures = AutoFailureBudget.Count,
                    events = RecoveryLog.Recent(), evidence = probeEvidence?.DeepClone() } };
    }

    private static object SafeHeartbeatStatus()
    {
        lock (Gate) return new { version = "CampusTerminal-1.3.19", phase, active = session != null,
            generation, heartbeatCount, loggingError = journal?.Error };
    }

    private static object Configure(int id, JsonObject request)
    {
        if (request["options"] is not JsonObject options) return new { ok = false, id, error = "InvalidOptions" };
        lock (Gate)
        {
            if (acceptanceActive) return new { ok = false, id, error = "AcceptanceOptionsLocked" };
            autoReconnect = options["autoReconnect"]?.GetValue<bool>() ?? autoReconnect;
            inodeFallback = options["inodeFallback"]?.GetValue<bool>() ?? inodeFallback;
            journal?.Write("OptionsChanged", new { autoReconnect, inodeFallback });
        }
        return Status(id);
    }

    private static Guid campusAdapter;

    private static void MaintainCampusRoute()
    {
        Guid id;
        lock (Gate) id = campusAdapter;
        if (id == Guid.Empty) return;
        if (Adapters.PhonePath(id) || Adapters.AlternativePath(id)) CampusRoute.Deprefer(id);
        else CampusRoute.Restore(id);
    }

    private static bool ReleaseCampusAddress(Guid adapter, string reason)
    {
        if (LiveGate.OriginalSuiteRunning() || LiveGate.OriginalGuiRunning()) return false;
        lock (Gate) campusAdapter = adapter;
        bool yielded = reason is "OtherNetwork" or "AlternativeNetworkPath" || Adapters.PhonePath(adapter);
        if (yielded) yielded = CampusRoute.Deprefer(adapter);
        bool released = DhcpRenew.Release(adapter);
        journal?.Write("CampusAddressReleased", new { released, yielded, reason });
        return released || yielded;
    }

    private static object ReleaseCampus(int id, JsonObject request)
    {
        var adapter = Adapters.Resolve(request["adapter"]?.GetValue<string>() ?? "");
        if (adapter == null) return new { ok = false, id, error = "AdapterNotFound" };
        bool busy;
        lock (Gate) { campusAdapter = adapter.Id; busy = session != null; }
        if (LiveGate.OriginalSuiteRunning() || LiveGate.OriginalGuiRunning())
            return new { ok = true, id, released = false, yielded = false, active = busy };
        // Move the default route before DHCP release. A live session must not lose
        // its address mid-send; the metric alone stops it beating the phone.
        bool yielded = CampusRoute.Deprefer(adapter.Id);
        bool released = false;
        if (!busy) released = DhcpRenew.Release(adapter.Id);
        journal?.Write("CampusAddressReleased", new { released, yielded, reason = "OtherNetwork", busy });
        return new { ok = true, id, released, yielded, active = busy };
    }

    private static object Disconnect(int id, bool shutdown)
    {
        lock (Gate)
        {
            if (handoffRunning) return new { ok = false, id, error = "HandoffInProgress" };
            if (phase == "fallback_failed") return new { ok = false, id, error = "HandoffFailed" };
            if (phase == "fallback_active") return new { ok = false, id, error = "OriginalOwnsNetwork" };
            stopIntent = HandoffTrigger.ManualDisconnect;
        }
        if (!StopSession()) { journal?.Write("SessionStopTimeout", new { id, method = "disconnect" }); return new { ok = false, id, error = "SessionStopTimeout" }; }
        RecoveryLog.EndCampaign();
        lock (Gate) { phase = "idle"; error = null; }
        if (shutdown) lifetime?.Cancel();
        return new { ok = true, id, phase = "idle" };
    }

    private static object Shutdown(int id, JsonObject request)
    {
        bool handback = request["handoff"]?.GetValue<bool>() == true;
        allowGuiResident = false;
        lock (Gate)
        {
            if (handback && session != null)
            {
                if (!handoffRunning)
                {
                    stopIntent = HandoffTrigger.ApplicationExit;
                    inodeFallback = true;
                    phase = "disconnecting";
                    session.Cancel();
                }
                return new { ok = true, id, pending = true, active = true, phase };
            }
            if (handback && phase == "fallback_failed")
                return new { ok = false, id, error = "HandoffFailed", report = handoffReport };
            if (handback && !handoffAttempted)
            {
                var adapter = Adapters.Resolve(request["adapter"]?.GetValue<string>() ?? "");
                if (adapter == null) return new { ok = false, id, error = "AdapterNotFound" };
                if (!LiveGate.Elevated()) return new { ok = false, id, error = "ElevationRequired" };
                var owned = new CancellationTokenSource();
                session = owned;
                handoffRunning = true;
                phase = "fallback";
                sessionTask = Task.Run(() => RunExitHandoff(adapter, owned));
                return new { ok = true, id, pending = true, active = true, phase };
            }
            // Tray/application exit without fallback must stop the host even if a
            // session or handoff is still winding down, so rebuilds can replace the exe.
            allowGuiResident = false;
            if (!handback)
            {
                stopIntent = HandoffTrigger.ManualDisconnect;
                phase = session != null ? "disconnecting" : phase;
                session?.Cancel();
            }
            lifetime?.Cancel();
            bool pending = sessionTask != null && !sessionTask.IsCompleted;
            return new { ok = true, id, pending, active = pending, phase, processId = Environment.ProcessId };
        }
    }

    private static object Connect(int id, JsonObject request)
    {
        var options = request["options"] as JsonObject;
        var acceptance = AcceptanceRequest.Parse(options?["acceptance"]);
        string type = options?["connectionType"]?.GetValue<string>() ?? "normal";
        if (type != "normal") return new { ok = false, id, error = "UnsupportedConnectionType" };
        var adapter = Adapters.Resolve(request["adapter"]?.GetValue<string>() ?? "");
        if (adapter == null) return new { ok = false, id, error = "AdapterNotFound" };
        if (!LiveGate.Elevated()) return new { ok = false, id, error = "ElevationRequired" };
        if (journal?.Error != null) return new { ok = false, id, error = journal.Error };
        bool takeOver = options?["takeOverOriginal"]?.GetValue<bool>() == true;
        bool manual = options?["manual"]?.GetValue<bool>() == true;
        // Only the new GUI marks automatic retries as manual=false. Older builds omit the
        // flag; refusing those would also disable the login button.
        bool automatic = options?["manual"] != null && !manual;
        bool silentRetry = options?["silentRetry"]?.GetValue<bool>() == true;
        bool reconnectCampaign = options?["autoReconnectCampaign"]?.GetValue<bool>() == true;
        string? campaignId = reconnectCampaign ? options?["campaignId"]?.GetValue<string>() : null;
        LocalCredentials? credentialsToRun = null;
        CancellationTokenSource? sessionToRun = null;
        if (acceptance == null && automatic && AutoFailureBudget.Blocked && !silentRetry)
        {
            lock (Gate) { attemptsExhausted = true; phase = "error"; error = firstError = "AutoReconnectLimit"; }
            ReleaseCampusAddress(adapter.Id, "RetryCap");
            journal?.Write("AutoReconnectLimit", new { autoFailures = AutoFailureBudget.Count });
            return new { ok = false, id, error = "AutoReconnectLimit" };
        }
        if (acceptance == null && automatic && Adapters.AlternativePath(adapter.Id))
        {
            ReleaseCampusAddress(adapter.Id, "OtherNetwork");
            lock (Gate) { phase = "idle"; error = "AlternativeNetworkPath"; attemptsExhausted = false; }
            journal?.Write("YieldedToOtherNetwork", new { adapter = adapter.Id, automatic = true });
            NotePaths(true);
            return new { ok = false, id, error = "AlternativeNetworkPath", alternative = true };
        }
        if (!takeOver && (LiveGate.OriginalSuiteRunning() || LiveGate.OriginalGuiRunning()))
            return new { ok = false, id, error = "OriginalClientRunning" };
        lock (Gate)
        {
            if (session != null) return new { ok = false, id, error = "AlreadyConnected" };
            LocalCredentials creds;
            try
            {
                creds = LocalCredentials.FromGui(request["username"]?.GetValue<string>() ?? "",
                    request["password"]?.GetValue<string>() ?? "");
            }
            catch (ArgumentException)
            {
                return new { ok = false, id, error = "UnsupportedCredentialEncoding" };
            }
            autoReconnect = acceptance == null && (options?["autoReconnect"]?.GetValue<bool>() ?? true);
            inodeFallback = acceptance != null || (options?["inodeFallback"]?.GetValue<bool>() ?? false);
            acceptanceActive = acceptance != null;
            firstError = null;
            heartbeatCount = 0;
            handoffAttempted = false; handoffReport = null;
            stopIntent = HandoffTrigger.RuntimeFailure;
            var owned = new CancellationTokenSource();
            session = owned;
            phase = "connecting"; error = null; generation = 0;
            probeEvidence = null;
            attempt = 0; attemptsExhausted = AutoFailureBudget.Blocked;
            connectSerial++;
            credentialsToRun = creds;
            sessionToRun = owned;
        }
        if (sessionToRun != null && credentialsToRun != null)
        {
            var launchCredentials = credentialsToRun;
            var launchSession = sessionToRun;
            if (reconnectCampaign) RecoveryLog.BeginCampaign(campaignId);
            else RecoveryLog.EndCampaign();
            diagnostics?.StartSession(Stopwatch.GetTimestamp());
            lock (Gate)
            {
                if (ReferenceEquals(session, launchSession))
                    sessionTask = Task.Run(() => RunSession(adapter, launchCredentials, launchSession, takeOver, acceptance));
            }
        }
        return new { ok = true, id, phase = "connecting" };
    }

    private static bool StopSession()
    {
        Task? task;
        lock (Gate)
        {
            if (session == null) return true;
            phase = "disconnecting";
            session.Cancel();
            task = sessionTask;
        }
        // Never release ownership/credentials while a sender is still running.
        return task == null || task.Wait(TimeSpan.FromSeconds(15));
    }

    private static void Note(string stage)
    {
        int currentGeneration;
        lock (Gate) currentGeneration = generation;
        if (stage.StartsWith("ProbeEvidence:", StringComparison.Ordinal))
            journal?.Write("ProbeEvidence", JsonNode.Parse(stage["ProbeEvidence:".Length..]));
        else journal?.Write(stage, new { generation = currentGeneration });
        lock (Gate)
        {
            if (stage == "AuthenticationRejected") firstError ??= stage;
            if (stage is "AuthenticationRejected" or "ProtocolFailed") CountAuthFailure();
            if (stage.StartsWith("LastConnectionFailure:", StringComparison.Ordinal))
                firstError ??= stage["LastConnectionFailure:".Length..];
            if (stage == "PeriodicHeartbeatSent") heartbeatCount++;
            if (stage.StartsWith("ConnectionAttemptStarted:", StringComparison.Ordinal))
                attempt = int.Parse(stage["ConnectionAttemptStarted:".Length..]);
            if (stage == "ReconnectAttemptsExhausted") attemptsExhausted = true;
            if (stage.StartsWith("ProbeEvidence:", StringComparison.Ordinal))
            {
                probeEvidence = new JsonObject { ["generation"] = generation, ["observedAt"] = DateTimeOffset.UtcNow.ToString("O"),
                    ["result"] = JsonNode.Parse(stage["ProbeEvidence:".Length..]) };
            }
            if (stage == "AuthenticationGenerationStarted") phase = generation == 0 ? "connecting" : "recovering";
            if (stage == "EapSuccessNotConnectivityVerified" || stage == "AuthenticatedAddressBound") phase = "verifying";
            if (stage == "TwoCampusRoundsPassed")
            {
                AutoFailureBudget.Reset();
                attemptsExhausted = false;
                firstError = null;
                phase = "online"; error = null;
            }
            if (stage is "CampusPartlyReachable" or "CampusDnsFailure" or "ProbeIndeterminate" or "TwoCampusRoundsUnavailable")
            { phase = "degraded"; error = stage; }
            if (stage == "RecoveryReauthenticating") phase = "recovering";
        }
        RecoveryLog.Observe(currentGeneration, stage);
    }

    private static void CountAuthFailure()
    {
        if (countedSerial == connectSerial) return;
        countedSerial = connectSerial;
        AutoFailureBudget.Record();
        if (!AutoFailureBudget.Blocked) return;
        attemptsExhausted = true;
        error = firstError = "AutoReconnectLimit";
    }

    internal static void ApplyProtocolStage(TrialAddressGate gate, string stage)
    {
        if (stage == "EapSuccessNotConnectivityVerified") gate.MarkAuthenticated();
        Note(stage);
    }

    private static void RunSession(AdapterInfo adapter, LocalCredentials creds, CancellationTokenSource owned, bool takeOver,
        AcceptanceRequest? acceptance = null)
    {
        bool acquired = false;
        bool sessionStarted = false;
        bool verifiedOnline = false;
        NpcapTransport? openedTransport = null;
        ObserverLease? lease = null;
        bool takeoverStarted = false;
        AcceptanceWatchdog? watchdog = null;
        var campaignClock = System.Diagnostics.Stopwatch.StartNew();
        Func<TimeSpan>? trialRemaining = acceptance == null ? null :
            () => TimeSpan.FromSeconds(acceptance.Seconds) - campaignClock.Elapsed;
        Func<TimeSpan>? totalRemaining = acceptance == null ? null :
            () => TimeSpan.FromSeconds(180) - campaignClock.Elapsed;
        lock (Gate) campusAdapter = adapter.Id;
        using var mutex = new Mutex(true, "Local\\CampusAuth-" + adapter.Id, out acquired);
        try
        {
            if (!acquired) throw new InvalidOperationException("ReplacementAlreadyRunning");
            if (acceptance != null)
                watchdog = AcceptanceWatchdog.Start(acceptance, reason =>
                {
                    lock (Gate) { firstError ??= reason; stopIntent = HandoffTrigger.ApplicationExit; }
                    journal?.Write(reason);
                    owned.Cancel();
                });
            var root = FindDataRoot();
            lease = new ObserverLease(Path.Combine(FindRepositoryRoot(root), "logs"));
            lease.WaitForPause(owned.Token);
            if (takeOver)
            {
                var original = new WindowsOriginalHandoff(FindRepositoryRoot(root), adapter, lease,
                    () => openedTransport == null, trialRemaining);
                lock (Gate) handoffReport = original.ReportDirectory;
                AcceptanceRecovery.Publish(acceptance, FindRepositoryRoot(root), lease, original.ReportDirectory);
                original.Preflight();
                owned.Token.ThrowIfCancellationRequested();
                takeoverStarted = true;
                journal?.Write("OriginalNormalStopRequested");
                if (acceptance != null) original.StopOriginalNormally();
                else original.StopOriginalService();
                journal?.Write("OriginalNormalStopVerified");
                bool linkReady = LiveGate.WaitUntilUp(adapter.Id, TimeSpan.FromSeconds(12), owned.Token);
                journal?.Write("LinkAfterOriginalStop", new { up = linkReady });
            }
            owned.Token.ThrowIfCancellationRequested();
            var gate = new TrialAddressGate(new(adapter.Id, adapter.Mac, adapter.Ipv4, "pending"));
            byte[] mac = Convert.FromHexString(adapter.Mac);
            using var transport = new NpcapTransport(adapter.Id, mac, allowSend: true);
            openedTransport = transport;
            var probe = new BoundRecoveryProbe(Path.Combine(root, "probes.json"));
            var settings = RecoverySettings.Load(Path.Combine(root, "recovery-settings.json"));
            var folder = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "CampusTerminal");
            Directory.CreateDirectory(folder);
            Protocol NewProtocol() => new(mac, creds.Username, creds.Password, new byte[4],
                BitConverter.ToUInt32(RandomNumberGenerator.GetBytes(4)), new H3cCrypto(), requireAddressBinding: true);
            TrialSnapshot? lastSnapshot = null;
            bool dhcpRequested = false;
            string? Block()
            {
                var snapshot = LiveGate.Capture(adapter.Id, lease.IsOwned);
                var blocked = gate.Observe(snapshot);
                if (snapshot != lastSnapshot)
                {
                    journal?.Write("AddressSnapshot", new { snapshot, blocked, bound = gate.BoundIdentity != null });
                    lastSnapshot = snapshot;
                }
                return blocked;
            }
            void Log(string stage)
            {
                ApplyProtocolStage(gate, stage);
            }
            bool Prepare(Protocol protocol)
            {
                if (protocol.AddressBound) return true;
                if (!dhcpRequested)
                {
                    dhcpRequested = true;
                    journal?.Write("DhcpRenewRequested", new { adapter = adapter.Id, ok = DhcpRenew.Request(adapter.Id) });
                }
                var identity = gate.BoundIdentity;
                if (identity == null) return false;
                protocol.BindAddress(IPAddress.Parse(identity.Ipv4).GetAddressBytes());
                Log("AuthenticatedAddressBound");
                return true;
            }
            ISessionMonitor? Monitor(int number)
            {
                var identity = gate.BoundIdentity ?? throw new InvalidOperationException("AddressNotBound");
                return new RecoveryMonitor(new InterfaceTrafficSampler(identity.Adapter, identity.Mac), probe, identity.Ipv4, Log,
                    requireVerification: true, settings: settings, recoveryEnabled: () => { lock (Gate) return autoReconnect; });
            }
            sessionStarted = true;
            var result = new ManagedSession(transport, new SessionClock(), NewProtocol, Block, Log, Prepare, Monitor,
                new RecoveryBudget(Path.Combine(folder, "recovery-budget.json"), () => DateTimeOffset.UtcNow),
                number => { dhcpRequested = false; lock (Gate) generation = number; Log("AuthenticationGenerationStarted"); },
                () => { lock (Gate) return autoReconnect; },
                () => diagnostics?.PulseSession(Stopwatch.GetTimestamp()))
                .Run(Timeout.InfiniteTimeSpan, owned.Token);
            verifiedOnline = result.Session.ConnectivityVerified && result.Session.EapAuthenticated;
            if (result.Session.Reason == "AlternativeNetworkPath" || AutoFailureBudget.Blocked || Adapters.PhonePath(adapter.Id))
                ReleaseCampusAddress(adapter.Id, Adapters.PhonePath(adapter.Id) ? "AlternativeNetworkPath" : result.Session.Reason ?? "SessionEnd");
            lock (Gate)
            {
                phase = result.Session.Reason == "Cancelled" ? "idle" : "error";
                error = result.Session.Reason == "Cancelled" ? null : result.Session.Reason;
                firstError ??= error;
            }
            if (result.Session.Reason is not (null or "Cancelled"))
                RecoveryLog.Finish(RecoveryLog.Short(result.Session.Reason));
            journal?.Write("SessionEnded", result);
            if (verifiedOnline) RecoveryLog.EndCampaign();
        }
        catch (OperationCanceledException) when (owned.IsCancellationRequested)
        {
            lock (Gate) { phase = "idle"; error = null; }
            journal?.Write("SessionCancelled");
        }
        catch (Exception ex)
        {
            lock (Gate)
            {
                phase = "error"; error = ClassifySessionError(ex); firstError ??= error;
            }
            RecoveryLog.Finish(RecoveryLog.Short(ClassifySessionError(ex)));
            journal?.Write("SessionError", SafeException(ex));
        }
        finally
        {
            watchdog?.Dispose();
            diagnostics?.StopSession();
            creds.Dispose();
            bool returnOriginal;
            // A failed tray-click takeover did not stop the original client. Do not
            // OCR-restore it or keep the observer paused while iNode still owns the link.
            lock (Gate) returnOriginal = acquired && lease != null && sessionStarted &&
                (OriginalHandoff.Required(inodeFallback, stopIntent, sessionStarted) ||
                 (acceptance != null && (takeoverStarted || sessionStarted))) &&
                error != "HandoffExecutorStillRunning" && error != "OriginalManualExitRequired" &&
                error != "AlternativeNetworkPath" &&
                (acceptance != null || error != "LinkUnavailable");
            // The transport's using scope has finished before any original-client action.
            try { openedTransport?.Dispose(); } catch (Exception) { }
            if (returnOriginal) PerformHandoff(adapter, lease!, () => true, totalRemaining, acceptance);
            else if (takeoverStarted && !verifiedOnline && stopIntent == HandoffTrigger.RuntimeFailure && lease != null
                     && inodeFallback)
                RestoreOriginalAfterFailedTakeover(adapter, lease);
            lease?.Dispose();
            lock (Gate)
            {
                if (ReferenceEquals(session, owned)) { session = null; sessionTask = null; }
                acceptanceActive = false;
                owned.Dispose();
            }
            if (acquired) mutex.ReleaseMutex();
        }
    }

    private static void RestoreOriginalAfterFailedTakeover(AdapterInfo adapter, ObserverLease lease)
    {
        try
        {
            string? report;
            lock (Gate) report = handoffReport;
            if (string.IsNullOrEmpty(report)) return;
            journal?.Write("OriginalServiceRestoreAfterFailure", new { report });
            var operations = new WindowsOriginalHandoff(FindRepositoryRoot(FindDataRoot()), adapter, lease, () => true,
                existingReport: report);
            operations.RestoreOriginalService();
            try { operations.StartOriginalNormally(); } catch (InvalidOperationException) { }
            journal?.Write("OriginalServiceRestoredAfterFailure");
        }
        catch (Exception ex)
        {
            journal?.Write("OriginalServiceRestoreFailed", SafeException(ex));
        }
    }

    private static void PerformHandoff(AdapterInfo adapter, ObserverLease lease, Func<bool> replacementStopped,
        Func<TimeSpan>? remaining = null, AcceptanceRequest? acceptance = null)
    {
        lock (Gate) { handoffRunning = true; handoffAttempted = true; phase = "fallback"; error = null; }
        lease.Preserve = true;
        try
        {
            // Exit can cancel the initial pause wait before any authentication starts.
            // Still require acknowledgement before restoring the other controller.
            using var pauseDeadline = new CancellationTokenSource();
            if (remaining != null)
            {
                var budget = remaining();
                if (budget <= TimeSpan.Zero) throw new InvalidOperationException("HandoffBudgetExhausted");
                pauseDeadline.CancelAfter(budget);
            }
            lease.WaitForPause(pauseDeadline.Token);
            var operations = new WindowsOriginalHandoff(FindRepositoryRoot(FindDataRoot()), adapter, lease, replacementStopped, remaining);
            lock (Gate) handoffReport = operations.ReportDirectory;
            AcceptanceRecovery.Publish(acceptance, FindRepositoryRoot(FindDataRoot()), lease, operations.ReportDirectory);
            var result = new OriginalHandoff(operations, stage =>
                File.AppendAllText(Path.Combine(operations.ReportDirectory, "stages.log"), DateTimeOffset.UtcNow.ToString("O") + " " + stage + Environment.NewLine)).Run();
            File.WriteAllText(Path.Combine(operations.ReportDirectory, "result.json"), System.Text.Json.JsonSerializer.Serialize(result));
            lock (Gate) { phase = result.Succeeded ? "fallback_active" : "fallback_failed"; error = result.Error; }
        }
        catch (Exception ex)
        {
            lock (Gate) { phase = "fallback_failed"; error = ex is InvalidOperationException ? ex.Message : ex.GetType().Name; }
        }
        finally { lock (Gate) handoffRunning = false; }
    }

    private static void RunExitHandoff(AdapterInfo adapter, CancellationTokenSource owned)
    {
        using var mutex = new Mutex(true, "Local\\CampusAuth-" + adapter.Id, out var acquired);
        ObserverLease? lease = null;
        try
        {
            if (!acquired) throw new InvalidOperationException("ReplacementAlreadyRunning");
            lease = new ObserverLease(Path.Combine(FindRepositoryRoot(FindDataRoot()), "logs"));
            lease.WaitForPause(owned.Token);
            PerformHandoff(adapter, lease, () => acquired);
        }
        catch (Exception ex)
        {
            lock (Gate) { handoffAttempted = true; phase = "fallback_failed"; error = ex is InvalidOperationException ? ex.Message : ex.GetType().Name; }
        }
        finally
        {
            lease?.Dispose();
            lock (Gate) { handoffRunning = false; session = null; sessionTask = null; owned.Dispose(); }
            if (acquired) mutex.ReleaseMutex();
        }
    }

    private static string ClassifySessionError(Exception ex)
    {
        var text = ex.Message ?? "";
        if (text.Contains("OpenPopup", StringComparison.Ordinal) ||
            text.Contains("ClickPopupText", StringComparison.Ordinal) ||
            text.Contains("PointerDidNotReachTarget", StringComparison.Ordinal) ||
            text.Contains("PopupChanged", StringComparison.Ordinal) ||
            text.Contains("PopupOccluded", StringComparison.Ordinal) ||
            text.Contains("TargetOccluded", StringComparison.Ordinal))
            return "OriginalManualExitRequired";
        return ex is InvalidOperationException ? text : ex.GetType().Name;
    }

    internal static string FindRepositoryRoot(string path)
    {
        if (!string.IsNullOrEmpty(path))
            for (var dir = new DirectoryInfo(path); dir != null; dir = dir.Parent)
                if (IsProductRoot(dir.FullName)) return dir.FullName;
        if (!string.IsNullOrEmpty(path) && Directory.Exists(path))
            return Path.GetFullPath(path);
        foreach (var start in RootSearchStarts(""))
            for (var dir = new DirectoryInfo(start); dir != null; dir = dir.Parent)
                if (IsProductRoot(dir.FullName)) return dir.FullName;
        throw new InvalidOperationException("ObserverInstallationMissing");
    }

    static bool IsProductRoot(string directory) =>
        File.Exists(Path.Combine(directory, "Supervise-Observation.ps1")) ||
        File.Exists(Path.Combine(directory, "CampusTerminal.portable"));

    private static IEnumerable<string> RootSearchStarts(string path)
    {
        if (!string.IsNullOrEmpty(path)) yield return path;
        string? exe = Path.GetDirectoryName(Environment.ProcessPath);
        if (!string.IsNullOrEmpty(exe)) yield return exe;
        yield return AppContext.BaseDirectory;
    }

    internal static string FirstExistingFile(params string[] paths)
    {
        foreach (var path in paths)
            if (!string.IsNullOrEmpty(path) && File.Exists(path)) return path;
        return paths.Length == 0 ? "" : paths[0];
    }

    private static void EnsureGuiResident()
    {
        if (!allowGuiResident || lifetime == null || lifetime.IsCancellationRequested) return;
        lock (Gate) if (handoffRunning) return;
        if (++heartbeatTicks < 2) return;
        string? dir = Path.GetDirectoryName(Environment.ProcessPath);
        if (string.IsNullOrEmpty(dir)) return;
        string gui = Path.Combine(dir, "CampusTerminal.exe");
        if (!File.Exists(gui)) return;
        var running = Process.GetProcessesByName("CampusTerminal");
        bool present = running.Length > 0;
        foreach (var process in running) process.Dispose();
        if (present) return;
        if (guiLaunchFails >= 5) return;
        if (DateTime.UtcNow - lastGuiLaunch < TimeSpan.FromSeconds(30)) return;
        using var gate = new Mutex(false, "Local\\CampusTerminal.GuiStart");
        bool owned = false;
        try
        {
            try { owned = gate.WaitOne(0); }
            catch (AbandonedMutexException) { owned = true; }
            if (!owned) return;
            var again = Process.GetProcessesByName("CampusTerminal");
            bool seen = again.Length > 0;
            foreach (var process in again) process.Dispose();
            if (seen) return;
            lastGuiLaunch = DateTime.UtcNow;
            var start = new ProcessStartInfo(gui)
            {
                Arguments = "--silent",
                WorkingDirectory = dir,
                UseShellExecute = true
            };
            using var launched = Process.Start(start);
            if (launched == null) { guiLaunchFails++; return; }
            guiLaunchFails = 0;
            journal?.Write("GuiResidentLaunched", new { pid = launched.Id });
        }
        catch (Exception ex)
        {
            guiLaunchFails++;
            journal?.Write("GuiResidentLaunchFailed", SafeException(ex));
        }
        finally { if (owned) gate.ReleaseMutex(); }
    }

    private static void RetireDuplicateAutostart()
    {
        try
        {
            string? dir = Path.GetDirectoryName(Environment.ProcessPath);
            if (string.IsNullOrEmpty(dir) || !File.Exists(Path.Combine(dir, "CampusTerminal.portable"))) return;
            // The portable logon entry is the HKCU Run key. This older task starts a second GUI.
            var start = new ProcessStartInfo("schtasks.exe", "/Delete /TN \"ReInode-CampusTerminal\" /F")
            { UseShellExecute = false, CreateNoWindow = true };
            using var process = Process.Start(start);
            process?.WaitForExit(4000);
        }
        catch (Exception) { }
    }

    private static string? lastPathCensus;
    private static int pathCensusTicks;

    private static void NotePaths(bool force)
    {
        try
        {
            var census = Adapters.Census(Guid.Empty);
            pathCensusTicks++;
            if (!force && census.Fingerprint == lastPathCensus && pathCensusTicks % 12 != 0) return;
            lastPathCensus = census.Fingerprint;
            journal?.Write("PathCensus", census.Detail);
        }
        catch (Exception) { }
    }

    private static void AllowOwnFirewall()
    {
        try
        {
            string? exe = Environment.ProcessPath;
            if (string.IsNullOrEmpty(exe) || !LiveGate.Elevated()) return;
            const string name = "CampusTerminal.Core";
            var show = new ProcessStartInfo("netsh", "advfirewall firewall show rule name=\"" + name + "\"")
            { UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true };
            using var listed = Process.Start(show);
            if (listed == null) return;
            string output = listed.StandardOutput.ReadToEnd();
            listed.WaitForExit(2000);
            if (listed.ExitCode == 0 && output.Contains(name, StringComparison.Ordinal)) return;
            foreach (string args in new[]
            {
                "advfirewall firewall add rule name=\"" + name + "\" dir=in action=allow program=\"" + exe + "\" profile=any enable=yes",
                "advfirewall firewall add rule name=\"" + name + " out\" dir=out action=allow program=\"" + exe + "\" profile=any enable=yes"
            })
            {
                var add = new ProcessStartInfo("netsh", args) { UseShellExecute = false, CreateNoWindow = true };
                using var added = Process.Start(add);
                added?.WaitForExit(3000);
            }
        }
        catch (Exception) { }
    }

    private static void RegisterHostTask()
    {
        try
        {
            string? exe = Environment.ProcessPath;
            if (string.IsNullOrEmpty(exe) || !LiveGate.Elevated()) return;
            string root = FindRepositoryRoot(FindDataRoot());
            string script = FirstExistingFile(
                Path.Combine(root, "CampusTerminal", "operations", "Register-HostTask.ps1"),
                Path.Combine(root, "operations", "Register-HostTask.ps1"));
            if (!File.Exists(script)) return;
            var start = new ProcessStartInfo("powershell.exe",
                "-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File \"" + script + "\" -Exe \"" + exe + "\"")
            { UseShellExecute = false, CreateNoWindow = true };
            using var process = Process.Start(start);
            process?.WaitForExit(20000);
        }
        catch (Exception) { }
    }

    private static string FindDataRoot()
    {
        foreach (var start in RootSearchStarts(AppContext.BaseDirectory))
            for (var dir = new DirectoryInfo(start); dir != null; dir = dir.Parent)
                if (File.Exists(Path.Combine(dir.FullName, "probes.json"))) return dir.FullName;
        throw new InvalidOperationException("BackendConfigurationMissing");
    }
}
