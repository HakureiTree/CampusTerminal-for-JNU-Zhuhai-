// SPDX-License-Identifier: GPL-3.0-or-later
namespace CampusAuth;

internal static class Program
{
    public static int Main(string[] args)
    {
        try
        {
            if (args.Length == 1 && args[0] == "gui-host") return GuiHost.Run();
            if (args.Length == 4 && args[0] == "recover-acceptance")
                return AcceptanceRecovery.Run(args[1], int.Parse(args[2]), int.Parse(args[3]));
            if (args.Length == 2 && args[0] == "probe-network")
            {
                var result = new BoundRecoveryProbe(Path.Combine(AppContext.BaseDirectory, "probes.json"))
                    .CheckAsync(args[1], CancellationToken.None).GetAwaiter().GetResult();
                Console.WriteLine(System.Text.Json.JsonSerializer.Serialize(result,
                    new System.Text.Json.JsonSerializerOptions { Converters = { new System.Text.Json.Serialization.JsonStringEnumConverter() } }));
                return result.Verified ? 0 : 1;
            }
            Console.Error.WriteLine("Usage: CampusTerminal.Core gui-host | probe-network <local-ipv4>");
            return 2;
        }
        catch (Exception ex) when (ex is IOException or InvalidOperationException or ArgumentException or InvalidDataException or FormatException)
        {
            Console.Error.WriteLine("Stopped: " + ex.GetType().Name);
            return 1;
        }
    }
}
