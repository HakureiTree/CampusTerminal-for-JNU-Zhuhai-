// SPDX-License-Identifier: GPL-3.0-or-later
using System.IO.Pipes;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace CampusAuth;

internal static class IpcServer
{
    public const string PipeName = "CampusTerminal.gui";
    internal static readonly JsonSerializerOptions Json = new()
    { PropertyNamingPolicy = JsonNamingPolicy.CamelCase, PropertyNameCaseInsensitive = true };

    public static void Listen(Func<JsonObject, object> handle, CancellationToken cancellation)
    {
        var security = new PipeSecurity();
        var user = WindowsIdentity.GetCurrent().User ?? throw new InvalidOperationException("MissingUserIdentity");
        security.SetAccessRuleProtection(true, false);
        security.AddAccessRule(new PipeAccessRule(user, PipeAccessRights.FullControl, AccessControlType.Allow));
        // Explicit same-user ACL; never grant all local users access to credentials.
        while (!cancellation.IsCancellationRequested)
        {
            using var pipe = NamedPipeServerStreamAcl.Create(PipeName, PipeDirection.InOut, 1,
                PipeTransmissionMode.Byte, PipeOptions.Asynchronous, 4096, 4096, security);
            try
            {
                pipe.WaitForConnectionAsync(cancellation).GetAwaiter().GetResult();
                using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
                timeout.CancelAfter(TimeSpan.FromSeconds(20));
                var line = ReadRequest(pipe, timeout.Token).GetAwaiter().GetResult();
                JsonObject request;
                try { request = JsonNode.Parse(line) as JsonObject ?? new JsonObject(); }
                catch (JsonException) { request = new JsonObject(); }
                object reply;
                try { reply = handle(request); }
                catch (Exception ex) when (ex is InvalidOperationException or ArgumentException or IOException or JsonException)
                { reply = new { ok = false, error = ex.GetType().Name, id = 0 }; }
                var bytes = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(reply, Json) + "\n");
                using var writeTimeout = new CancellationTokenSource(TimeSpan.FromSeconds(2));
                pipe.WriteAsync(bytes, writeTimeout.Token).AsTask().GetAwaiter().GetResult();
            }
            catch (OperationCanceledException) { if (cancellation.IsCancellationRequested) return; }
            catch (IOException) { }
            catch (DecoderFallbackException) { }
        }
    }

    private static async Task<string> ReadRequest(Stream stream, CancellationToken token)
    {
        using var buffer = new MemoryStream();
        var chunk = new byte[1024];
        while (buffer.Length <= 16384)
        {
            int count = await stream.ReadAsync(chunk, token);
            if (count == 0) throw new IOException("PipeClosed");
            int end = Array.IndexOf(chunk, (byte)'\n', 0, count);
            buffer.Write(chunk, 0, end < 0 ? count : end);
            if (buffer.Length > 16384) break;
            if (end >= 0) return new UTF8Encoding(false, true).GetString(buffer.ToArray());
        }
        throw new IOException("RequestTooLarge");
    }
}
