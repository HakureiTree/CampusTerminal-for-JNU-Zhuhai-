// SPDX-License-Identifier: GPL-3.0-or-later
using System.Text.Json;

namespace CampusAuth;

internal sealed record RecoverySettings(int BaselineSamples = 20, int LowSamples = 3,
    double DropFraction = .8, double MinimumBytesPerSecond = 8192, int HealthCheckSeconds = 60)
{
    public void Validate()
    {
        if (BaselineSamples is < 5 or > 120 || LowSamples is < 2 or > 10 ||
            !double.IsFinite(DropFraction) || DropFraction is < .5 or > .99 ||
            !double.IsFinite(MinimumBytesPerSecond) || MinimumBytesPerSecond is < 1024 or > 1000000000 ||
            HealthCheckSeconds is < 30 or > 300)
            throw new InvalidDataException("Invalid campus recovery settings.");
    }
    public static RecoverySettings Load(string path)
    {
        var settings = JsonSerializer.Deserialize<RecoverySettings>(File.ReadAllText(path))
            ?? throw new InvalidDataException("Missing recovery settings.");
        settings.Validate();
        return settings;
    }
}
