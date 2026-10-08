// SPDX-License-Identifier: GPL-3.0-or-later
using System.Net;
using System.Net.Sockets;
using System.Text.Json;

namespace CampusAuth;

internal enum ProbeOutcome { Reachable, TransportFailure, Indeterminate, DnsFailure, TlsFailure, LocalFailure }
internal sealed record ProbeRound(ProbeOutcome[] Tcp, ProbeOutcome[] Https);
internal sealed record RecoveryEvidence(bool Unavailable, bool Verified, string Reason, ProbeRound[]? Rounds = null);
internal interface IRecoveryProbe
{
    Task<RecoveryEvidence> CheckAsync(string localAddress, CancellationToken cancellation);
}

internal sealed class BoundRecoveryProbe : IRecoveryProbe
{
    private readonly IPEndPoint[] tcp;
    private readonly Uri[] https;
    public BoundRecoveryProbe(string configPath)
    {
        using var config = JsonDocument.Parse(File.ReadAllText(configPath));
        tcp = config.RootElement.GetProperty("TcpTargets").EnumerateArray().Select(t =>
            new IPEndPoint(IPAddress.Parse(t.GetProperty("Address").GetString()!), t.GetProperty("Port").GetInt32())).ToArray();
        https = config.RootElement.GetProperty("HttpTargets").EnumerateArray().Select(t =>
            new Uri(t.GetProperty("Url").GetString()!)).ToArray();
        if (tcp.Length < 2 || tcp.Length > 8 || https.Length < 2 || https.Length > 8 ||
            tcp.Select(t => t.Address).Distinct().Count() < 2 || https.Select(u => u.Host).Distinct().Count() < 2 ||
            tcp.Any(t => t.AddressFamily != AddressFamily.InterNetwork) ||
            https.Any(u => u.Scheme != "https" || u.UserInfo.Length != 0))
            throw new InvalidDataException("Recovery probe requires independent IPv4 TCP and HTTPS targets.");
    }

    internal static RecoveryEvidence Classify(IReadOnlyList<ProbeRound> rounds)
    {
        if (rounds.Count != 2 || rounds.Any(r => r.Tcp.Length < 2 || r.Https.Length < 2))
            return new(false, false, "IncompleteProbe");
        bool verified = rounds.All(r => r.Tcp.All(x => x == ProbeOutcome.Reachable) &&
            r.Https.Count(x => x == ProbeOutcome.Reachable) >= 2);
        // An outage also prevents uncached DNS lookups. Do not require DNS to
        // succeed before recognizing failure of every independent bound TCP target.
        bool unavailable = rounds.All(r => r.Tcp.All(x => x == ProbeOutcome.TransportFailure) &&
            r.Https.All(x => x is ProbeOutcome.TransportFailure or ProbeOutcome.DnsFailure));
        bool dnsFailure = rounds.All(r => r.Tcp.All(x => x == ProbeOutcome.Reachable) &&
            r.Https.All(x => x == ProbeOutcome.DnsFailure));
        return new(unavailable, verified, verified ? "TwoCampusRoundsPassed" : unavailable ?
            "TwoCampusRoundsUnavailable" : dnsFailure ? "CampusDnsFailure" : rounds.Any(r => r.Tcp.Concat(r.Https).Contains(ProbeOutcome.Reachable)) ?
            "CampusPartlyReachable" : "ProbeIndeterminate", rounds.ToArray());
    }

    public async Task<RecoveryEvidence> CheckAsync(string localAddress, CancellationToken cancellation)
    {
        var local = IPAddress.Parse(localAddress);
        if (!TrialAddressGate.UsableIpv4(localAddress)) return new(false, false, "AddressUnavailable");
        var rounds = new List<ProbeRound>();
        for (int round = 0; round < 2; round++)
        {
            var tcpWork = tcp.Select(t => Tcp(local, t, cancellation)).ToArray();
            var httpWork = https.Select(u => Https(local, u, cancellation)).ToArray();
            try
            {
                await Task.WhenAll(tcpWork.Concat(httpWork));
                rounds.Add(new(tcpWork.Select(t => t.Result).ToArray(), httpWork.Select(t => t.Result).ToArray()));
                if (round == 0) await Task.Delay(1000, cancellation);
            }
            catch (OperationCanceledException) when (cancellation.IsCancellationRequested)
            {
                if (rounds.Count <= round)
                    rounds.Add(new(tcpWork.Select(CompletedOutcome).ToArray(), httpWork.Select(CompletedOutcome).ToArray()));
                return new(false, false, "ProbeCancelled", rounds.ToArray());
            }
        }
        return Classify(rounds);
    }

    private static ProbeOutcome CompletedOutcome(Task<ProbeOutcome> task) =>
        task.IsCompletedSuccessfully ? task.Result : ProbeOutcome.Indeterminate;

    private static bool RemoteFailure(SocketException ex) => ex.SocketErrorCode is
        SocketError.TimedOut or SocketError.NetworkUnreachable or SocketError.HostUnreachable;

    private static async Task<ProbeOutcome> Tcp(IPAddress local, IPEndPoint remote, CancellationToken cancellation)
    {
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
        timeout.CancelAfter(TimeSpan.FromSeconds(2));
        using var client = new TcpClient(AddressFamily.InterNetwork);
        try
        {
            client.Client.Bind(new IPEndPoint(local, 0));
            await client.ConnectAsync(remote.Address, remote.Port, timeout.Token);
            return ProbeOutcome.Reachable;
        }
        catch (OperationCanceledException) when (!cancellation.IsCancellationRequested) { return ProbeOutcome.TransportFailure; }
        catch (SocketException ex) { return RemoteFailure(ex) ? ProbeOutcome.TransportFailure : ProbeOutcome.LocalFailure; }
    }

    private static async Task<ProbeOutcome> Https(IPAddress local, Uri uri, CancellationToken cancellation)
    {
        bool resolved = false;
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
        timeout.CancelAfter(TimeSpan.FromSeconds(5));
        using var handler = new SocketsHttpHandler { UseProxy = false, AllowAutoRedirect = false, UseCookies = false };
        handler.ConnectCallback = async (context, token) =>
        {
            var addresses = await Dns.GetHostAddressesAsync(context.DnsEndPoint.Host, AddressFamily.InterNetwork, token);
            if (addresses.Length == 0) throw new SocketException((int)SocketError.HostNotFound);
            resolved = true;
            var socket = new Socket(AddressFamily.InterNetwork, SocketType.Stream, ProtocolType.Tcp);
            try
            {
                socket.Bind(new IPEndPoint(local, 0));
                await socket.ConnectAsync(addresses, context.DnsEndPoint.Port, token);
                return new NetworkStream(socket, ownsSocket: true);
            }
            catch { socket.Dispose(); throw; }
        };
        using var client = new HttpClient(handler) { Timeout = Timeout.InfiniteTimeSpan };
        try
        {
            using var request = new HttpRequestMessage(HttpMethod.Head, uri);
            using var response = await client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, timeout.Token);
            return ProbeOutcome.Reachable; // TLS validation remains enabled; status codes are not login evidence.
        }
        catch (OperationCanceledException) when (!cancellation.IsCancellationRequested)
        { return resolved ? ProbeOutcome.TransportFailure : ProbeOutcome.DnsFailure; }
        catch (HttpRequestException ex)
        {
            if (ex.HttpRequestError == HttpRequestError.NameResolutionError) return ProbeOutcome.DnsFailure;
            if (ex.HttpRequestError == HttpRequestError.SecureConnectionError) return ProbeOutcome.TlsFailure;
            return ex.InnerException is SocketException socket && RemoteFailure(socket) ? ProbeOutcome.TransportFailure : ProbeOutcome.Indeterminate;
        }
    }
}
