// SPDX-License-Identifier: GPL-3.0-or-later
using System.Text.Json.Nodes;

namespace CampusAuth;

internal static class RecoveryLog
{
    private const int Capacity = 100;
    private static readonly object Sync = new();
    private static readonly List<JsonObject> Rows = new();
    private static string? store;
    private static Action<string>? diagnosis;
    private static string? activeCampaign;
    private static bool corruptSourceUnpreserved;
    internal static Func<string, bool>? QuarantineFailureForTests { get; set; }
    private static string? error;
    internal static string? Error { get { lock (Sync) return error; } }

    internal static void UseStore(string? path, Action<string>? onDiagnosis = null)
    {
        string? issue = null;
        lock (Sync)
        {
            store = path; diagnosis = onDiagnosis; Rows.Clear(); activeCampaign = null;
            corruptSourceUnpreserved = false; error = null;
            if (string.IsNullOrEmpty(path) || !File.Exists(path)) return;
            try
            {
                if (JsonNode.Parse(File.ReadAllText(path)) is not JsonArray list) throw new System.Text.Json.JsonException();
                foreach (var item in list.OfType<JsonObject>().TakeLast(Capacity)) Rows.Add((JsonObject)item.DeepClone());
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or System.Text.Json.JsonException)
            {
                error = "RecoveryLogUnavailable"; issue = ex.GetType().Name; corruptSourceUnpreserved = true;
                Rows.Clear();
                if (TryPreserveCorruptSource()) corruptSourceUnpreserved = false;
                else issue = "QuarantineUnavailable";
            }
        }
        if (issue != null) Report(issue);
    }

    internal static void Reset() { lock (Sync) { Rows.Clear(); activeCampaign = null; } }
    internal static JsonObject[] Recent()
    { lock (Sync) return Rows.TakeLast(Capacity).Select(row => (JsonObject)row.DeepClone()).ToArray(); }

    internal static bool BeginCampaign(string? campaignId)
    {
        string? issue = null;
        bool added = false;
        lock (Sync)
        {
            if (!IsSafeCampaignId(campaignId)) { activeCampaign = null; return false; }
            var existing = Rows.LastOrDefault(row => row["campaignId"]?.GetValue<string>() == campaignId);
            activeCampaign = campaignId;
            if (existing != null)
            {
                if (existing["result"]?.GetValue<string>() != "重连中")
                {
                    var refreshedAt = DateTimeOffset.Now;
                    existing["at"] = refreshedAt.ToString("M.d"); existing["time"] = refreshedAt.ToString("HH:mm:ss");
                    existing["result"] = "重连中"; issue = SaveLocked();
                }
            }
            else
            {
                Rows.Add(NewRow(campaignId!)); Trim(); added = true; issue = SaveLocked();
            }
        }
        if (issue != null) Report(issue);
        return added;
    }

    internal static void EndCampaign() { lock (Sync) { activeCampaign = null; } }

    internal static void Observe(int generation, string stage)
    {
        string? issue = null;
        lock (Sync)
        {
            if (stage == "AuthenticationGenerationStarted" && generation > 0 && activeCampaign == null)
            {
                activeCampaign = "internal-" + Guid.NewGuid().ToString("N");
                Rows.Add(NewRow(activeCampaign)); Trim(); issue = SaveLocked();
            }
            if (activeCampaign != null)
            {
                if (stage == "TwoCampusRoundsPassed") issue = FinishLocked("成功") ?? issue;
                else if (stage is "ReconnectAttemptsExhausted" or "AutoReconnectLimit") issue = FinishLocked("失败") ?? issue;
                else if (stage.StartsWith("LastConnectionFailure:", StringComparison.Ordinal))
                    issue = FinishLocked(Short(stage["LastConnectionFailure:".Length..])) ?? issue;
            }
        }
        if (issue != null) Report(issue);
    }

    internal static void Finish(string result)
    {
        string? issue;
        lock (Sync) issue = FinishLocked(result);
        if (issue != null) Report(issue);
    }

    private static string? FinishLocked(string result)
    {
        if (activeCampaign == null) return null;
        var row = Rows.LastOrDefault(row => row["campaignId"]?.GetValue<string>() == activeCampaign);
        if (row == null || row["result"]?.GetValue<string>() != "重连中") { activeCampaign = null; return null; }
        row["result"] = result;
        activeCampaign = null;
        return SaveLocked();
    }

    private static bool IsSafeCampaignId(string? value) => !string.IsNullOrWhiteSpace(value) && value.Length <= 128 &&
        value.All(character => char.IsAsciiLetterOrDigit(character) && character <= 127 || character is '-' or '_');

    private static JsonObject NewRow(string campaignId)
    {
        var now = DateTimeOffset.Now;
        return new JsonObject { ["at"] = now.ToString("M.d"), ["time"] = now.ToString("HH:mm:ss"),
            ["result"] = "重连中", ["campaignId"] = campaignId };
    }

    private static void Trim() { while (Rows.Count > Capacity) Rows.RemoveAt(0); }
    private static string? SaveLocked()
    {
        if (string.IsNullOrEmpty(store)) return null;
        string temp = store + ".tmp";
        try
        {
            if (corruptSourceUnpreserved)
            {
                if (!TryPreserveCorruptSource()) throw new IOException("CorruptRecoverySourceNotPreserved");
                corruptSourceUnpreserved = false;
            }
            var parent = Path.GetDirectoryName(store);
            if (!string.IsNullOrEmpty(parent)) Directory.CreateDirectory(parent);
            File.WriteAllText(temp, new JsonArray(Rows.Select(row => row.DeepClone()).ToArray()).ToJsonString());
            File.Move(temp, store, overwrite: true);
            error = null;
            return null;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or System.Text.Json.JsonException)
        {
            error = "RecoveryLogUnavailable";
            try { if (File.Exists(temp)) File.Delete(temp); }
            catch (Exception cleanError) when (cleanError is IOException or UnauthorizedAccessException) { }
            return ex.GetType().Name;
        }
    }

    private static bool TryPreserveCorruptSource()
    {
        if (string.IsNullOrEmpty(store) || !File.Exists(store)) return true;
        if (QuarantineFailureForTests?.Invoke(store) == true) return false;
        try { File.Copy(store, store + ".corrupt-" + Guid.NewGuid().ToString("N"), overwrite: false); return true; }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { return false; }
    }

    private static void Report(string type)
    {
        var callback = diagnosis;
        if (callback == null) return;
        ThreadPool.QueueUserWorkItem(_ =>
        {
            try { callback("RecoveryLogUnavailable:" + type); }
            catch (Exception) { }
        });
    }

    internal static string Short(string? reason) => reason switch
    {
        null or "" or "Cancelled" => "失败",
        "AuthenticationRejected" => "拒绝",
        "LinkUnavailable" => "断线",
        "AlternativeNetworkPath" => "让出",
        "ReconnectAttemptsExhausted" or "AutoReconnectLimit" => "失败",
        var text when text.Contains("Timeout", StringComparison.Ordinal) => "超时",
        _ => "失败"
    };
}
