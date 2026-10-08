// SPDX-License-Identifier: GPL-3.0-or-later
using System.Text.Json;

namespace CampusAuth;

internal interface IRecoveryBudget
{
    string? Reserve();
    void Trip();
}

internal sealed record RecoveryBudgetState(DateTimeOffset[] Attempts, bool CircuitOpen);

// A reservation is durable before Logoff. A failed or interrupted attempt remains
// charged across process restarts. The circuit requires explicit operator repair.
internal sealed class RecoveryBudget(string path, Func<DateTimeOffset> utcNow) : IRecoveryBudget
{
    private RecoveryBudgetState Read()
    {
        if (!File.Exists(path)) return new([], false);
        var state = JsonSerializer.Deserialize<RecoveryBudgetState>(File.ReadAllText(path));
        if (state?.Attempts == null || state.Attempts.Length > 3 ||
            state.Attempts.Any(t => t > utcNow().AddSeconds(2))) throw new InvalidDataException("Invalid recovery budget.");
        return state;
    }

    internal static string? Block(RecoveryBudgetState state, DateTimeOffset now)
    {
        if (state.CircuitOpen) return "RecoveryCircuitOpen";
        if (state.Attempts.Any(t => now - t < TimeSpan.FromSeconds(600))) return "RecoveryCooldown";
        if (state.Attempts.Count(t => t.ToOffset(TimeSpan.FromHours(8)).Date == now.ToOffset(TimeSpan.FromHours(8)).Date) >= 3)
            return "RecoveryDailyLimit";
        return null;
    }

    private void Save(RecoveryBudgetState state)
    {
        var temp = path + ".tmp";
        using (var stream = new FileStream(temp, FileMode.Create, FileAccess.Write, FileShare.None))
        {
            JsonSerializer.Serialize(stream, state);
            stream.Flush(flushToDisk: true);
        }
        File.Move(temp, path, overwrite: true);
    }

    public string? Reserve()
    {
        try
        {
            using var ownership = new FileStream(path + ".lock", FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
            var now = utcNow();
            var state = Read();
            var blocked = Block(state, now);
            if (blocked != null) return blocked;
            var today = now.ToOffset(TimeSpan.FromHours(8)).Date;
            Save(new(state.Attempts.Where(t => t.ToOffset(TimeSpan.FromHours(8)).Date == today).Append(now).ToArray(), false));
            return null;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or JsonException)
        { return "RecoveryBudgetUnavailable"; }
    }

    public void Trip()
    {
        using var ownership = new FileStream(path + ".lock", FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
        Save(Read() with { CircuitOpen = true });
    }
}
