// SPDX-License-Identifier: GPL-3.0-or-later
using System.Net.NetworkInformation;

namespace CampusAuth;

internal sealed record TrafficSample(TimeSpan At, long Received, long Sent);
internal interface ITrafficSampler { TrafficSample Read(TimeSpan now); }

// Counts every application's traffic on the campus interface, without counting
// the same payload again on a proxy/TUN interface. No packet capture is needed.
internal sealed class InterfaceTrafficSampler(Guid adapter, string mac) : ITrafficSampler
{
    public TrafficSample Read(TimeSpan now)
    {
        var matches = NetworkInterface.GetAllNetworkInterfaces()
            .Where(n => Guid.TryParse(n.Id, out var id) && id == adapter).ToArray();
        if (matches.Length != 1 || matches[0].OperationalStatus != OperationalStatus.Up ||
            !matches[0].GetPhysicalAddress().ToString().Equals(mac, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("TrafficInterfaceChanged");
        var stats = matches[0].GetIPStatistics();
        return new(now, stats.BytesReceived, stats.BytesSent);
    }
}

internal sealed class TrafficDropDetector(int baselineSamples = 20, int lowSamples = 3,
    double dropFraction = .8, double minimumBytesPerSecond = 8192)
{
    private readonly Queue<double> baseline = new();
    private TrafficSample? previous;
    private int low;
    public double Rate { get; private set; }
    public double Baseline { get; private set; }

    public void Reset() { baseline.Clear(); previous = null; low = 0; Rate = Baseline = 0; }

    public bool Observe(TrafficSample sample)
    {
        if (baselineSamples < 2 || lowSamples < 1 || dropFraction <= 0 || dropFraction >= 1 || minimumBytesPerSecond <= 0)
            throw new ArgumentOutOfRangeException(nameof(baselineSamples));
        var old = previous;
        previous = sample;
        if (old == null) return false;
        double seconds = (sample.At - old.At).TotalSeconds;
        if (seconds < .5 || seconds > 3 || sample.Received < old.Received || sample.Sent < old.Sent ||
            sample.Received < 0 || sample.Sent < 0)
        {
            Reset(); previous = sample; return false;
        }
        Rate = ((double)(sample.Received - old.Received) + (sample.Sent - old.Sent)) / seconds;
        if (baseline.Count == baselineSamples)
        {
            var sorted = baseline.Order().ToArray();
            Baseline = (sorted[(sorted.Length - 1) / 2] + sorted[sorted.Length / 2]) / 2;
            if (Baseline >= minimumBytesPerSecond && Rate <= Baseline * (1 - dropFraction + 1e-12))
                return ++low == lowSamples; // Freeze the baseline during the suspected outage.
        }
        low = 0;
        baseline.Enqueue(Rate);
        if (baseline.Count > baselineSamples) baseline.Dequeue();
        return false;
    }
}
