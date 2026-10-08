// SPDX-License-Identifier: GPL-3.0-or-later
using System.Text.Json.Nodes;

namespace CampusAuth;

internal static class RecoveryLog
{
    private static readonly List<JsonObject> Rows = new();
    private static string? store;

    internal static void UseStore(string? path)
    {
        store = path;
        Rows.Clear();
        if (string.IsNullOrEmpty(path) || !File.Exists(path)) return;
        try
        {
            if (JsonNode.Parse(File.ReadAllText(path)) is not JsonArray list) return;
            foreach (var item in list.OfType<JsonObject>().TakeLast(3))
                Rows.Add((JsonObject)item.DeepClone());
        }
        catch (Exception) { Rows.Clear(); }
    }

    internal static void Reset() => Rows.Clear();

    internal static JsonObject[] Recent()
    {
        return Rows.TakeLast(3).Select(row => (JsonObject)row.DeepClone()).ToArray();
    }

    internal static void Observe(int generation, string stage)
    {
        if (generation <= 0) return;
        if (stage == "AuthenticationGenerationStarted")
        {
            Add("重连中");
            return;
        }
        if (stage == "TwoCampusRoundsPassed")
        {
            if (Rows.Count == 0 || Rows[^1]["result"]?.GetValue<string>() != "重连中")
                Add("成功");
            else
                Finish("成功");
            return;
        }
        if (stage is "ReconnectAttemptsExhausted" or "AutoReconnectLimit")
            Finish("失败");
    }

    internal static void Finish(string result)
    {
        if (Rows.Count == 0 || Rows[^1]["result"]?.GetValue<string>() != "重连中") return;
        Rows[^1]["result"] = result;
        Save();
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

    private static void Add(string result)
    {
        Rows.Add(new JsonObject
        {
            ["at"] = DateTimeOffset.Now.ToString("M.d"),
            ["time"] = DateTimeOffset.Now.ToString("HH:mm:ss"),
            ["result"] = result
        });
        while (Rows.Count > 3) Rows.RemoveAt(0);
        Save();
    }

    private static void Save()
    {
        if (string.IsNullOrEmpty(store)) return;
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(store)!);
            File.WriteAllText(store, new JsonArray(Rows.Select(row => row.DeepClone()).ToArray()).ToJsonString());
        }
        catch (Exception) { }
    }
}
