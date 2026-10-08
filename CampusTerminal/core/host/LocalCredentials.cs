// SPDX-License-Identifier: GPL-3.0-or-later
using System.Security.Cryptography;

namespace CampusAuth;

internal sealed class LocalCredentials : IDisposable
{
    public string Username { get; }
    public byte[] Password { get; }
    public LocalCredentials(string username, byte[] password)
    {
        if (username.Length is < 1 or > 128 || username.Any(c => c < 33 || c > 126) || password.Length is < 1 or > 128)
            throw new ArgumentException("Unsupported credential length or username encoding.");
        Username = username; Password = password.ToArray();
    }

    private static ConsoleKeyInfo ReadKey(Func<bool> cancelled)
    {
        while (!Console.KeyAvailable)
        {
            if (cancelled()) throw new OperationCanceledException();
            Thread.Sleep(50);
        }
        if (cancelled()) throw new OperationCanceledException();
        return Console.ReadKey(intercept: true);
    }

    public static LocalCredentials FromGui(string username, string password)
    {
        if (password.Any(c => c < 32 || c > 126))
            throw new ArgumentException("UnsupportedCredentialEncoding");
        var bytes = System.Text.Encoding.ASCII.GetBytes(password);
        try { return new LocalCredentials(username, bytes); }
        finally { CryptographicOperations.ZeroMemory(bytes); }
    }

    public static LocalCredentials Prompt(Func<bool> cancelled)
    {
        if (Console.IsInputRedirected || Console.IsOutputRedirected)
            throw new InvalidOperationException("Credentials require a local interactive console.");
        Console.WriteLine("Experimental campus client. Credentials stay in memory; ESC cancels.");
        Console.Write("Student account: ");
        var account = new System.Text.StringBuilder();
        while (true)
        {
            var key = ReadKey(cancelled);
            if (key.Key == ConsoleKey.Escape) throw new OperationCanceledException();
            if (key.Key == ConsoleKey.Enter) break;
            if (key.Key == ConsoleKey.Backspace)
            {
                if (account.Length > 0) { account.Length--; Console.Write("\b \b"); }
                continue;
            }
            if (key.KeyChar == '\0') continue;
            if (key.KeyChar is < '!' or > '~' || account.Length == 128) throw new ArgumentException("Unsupported account input.");
            account.Append(key.KeyChar); Console.Write(key.KeyChar);
        }
        var username = account.ToString();
        Console.WriteLine();
        Console.Write("Password (not displayed): ");
        var buffer = new byte[128];
        int count = 0;
        try
        {
            while (true)
            {
                var key = ReadKey(cancelled);
                if (key.Key == ConsoleKey.Escape) throw new OperationCanceledException();
                if (key.Key == ConsoleKey.Enter) break;
                if (key.Key == ConsoleKey.Backspace) { if (count > 0) buffer[--count] = 0; continue; }
                if (key.KeyChar == '\0') continue;
                if (key.KeyChar is < ' ' or > '~' || count == buffer.Length)
                    throw new ArgumentException("This experimental profile accepts at most 128 ASCII password bytes.");
                buffer[count++] = (byte)key.KeyChar;
            }
            Console.WriteLine();
            var password = buffer.AsSpan(0, count).ToArray();
            try { return new LocalCredentials(username, password); }
            finally { CryptographicOperations.ZeroMemory(password); }
        }
        finally { CryptographicOperations.ZeroMemory(buffer); }
    }

    public void Dispose() => CryptographicOperations.ZeroMemory(Password);
}
