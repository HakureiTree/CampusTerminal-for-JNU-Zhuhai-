// SPDX-License-Identifier: GPL-3.0-or-later
using System.Buffers.Binary;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;

namespace CampusAuth;

internal interface IFrameTransport : IDisposable
{
    byte[]? Poll();
    void Send(byte[] frame);
}

internal static class FrameScope
{
    public static bool Incoming(ReadOnlySpan<byte> frame, ReadOnlySpan<byte> local) => frame.Length >= 18 &&
        frame[12] == 0x88 && frame[13] == 0x8e &&
        (frame[..6].SequenceEqual(local) || frame.Slice(6, 6).SequenceEqual(local));

    public static bool Outgoing(ReadOnlySpan<byte> frame, ReadOnlySpan<byte> local)
    {
        if (frame.Length is < 18 or > 1024 || !frame.Slice(6, 6).SequenceEqual(local) ||
            frame[12] != 0x88 || frame[13] != 0x8e || frame[14] != 1 ||
            BinaryPrimitives.ReadUInt16BigEndian(frame[16..]) != frame.Length - 18) return false;
        if (frame[15] is 1 or 2) return frame.Length == 18;
        return frame[15] == 0 && frame.Length >= 23 && frame[18] == 2 && frame[22] is 1 or 4 &&
               BinaryPrimitives.ReadUInt16BigEndian(frame[20..]) == frame.Length - 18;
    }
}

internal sealed class NpcapTransport : IFrameTransport
{
    private readonly byte[] local;
    private readonly bool allowSend;
    private IntPtr library, handle;
    private readonly Close close;
    private readonly Next next;
    private readonly SendPacket send;
    public string Version { get; }
    internal bool IsClosed => handle == IntPtr.Zero;

    public NpcapTransport(Guid adapter, byte[] local, bool allowSend = false)
    {
        if (!OperatingSystem.IsWindows() || !Environment.Is64BitProcess) throw new PlatformNotSupportedException();
        if (local.Length != 6 || local.All(b => b == 0) || (local[0] & 1) != 0) throw new ArgumentException("Invalid local MAC.");
        this.local = local.ToArray(); this.allowSend = allowSend;
        var directory = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "Npcap");
        VerifyLibrary(Path.Combine(directory, "wpcap.dll"), "AA2C63A5A0B732E2AAEC6660F5D97727D857FCFD315084940859E5FE71A65C24");
        VerifyLibrary(Path.Combine(directory, "Packet.dll"), "1181BA48394DFD64E281D43850E41355BD6A0ED2523819980820221C0BE09D74");
        library = LoadLibraryExW(Path.Combine(directory, "wpcap.dll"), IntPtr.Zero, 0x100 | 0x800);
        if (library == IntPtr.Zero) throw new IOException("Cannot load verified Npcap library.");
        try
        {
            close = Function<Close>("pcap_close"); next = Function<Next>("pcap_next_ex");
            send = Function<SendPacket>("pcap_sendpacket");
            Version = Marshal.PtrToStringAnsi(Function<LibraryVersion>("pcap_lib_version")()) ?? "Unknown";
            var error = new StringBuilder(256);
            handle = Function<Open>("pcap_open_live")($"\\Device\\NPF_{{{adapter.ToString().ToUpperInvariant()}}}", 65535, 0, 100, error);
            if (handle == IntPtr.Zero) throw new IOException("Cannot open the campus capture device.");
            if (Function<DataLink>("pcap_datalink")(handle) != 1) throw new IOException("Non-Ethernet device.");
            var filter = new BpfProgram();
            var expression = "ether proto 0x888e and ether host " + string.Join(":", local.Select(b => b.ToString("x2")));
            if (Function<Compile>("pcap_compile")(handle, ref filter, expression, 1, uint.MaxValue) != 0)
                throw new IOException("Cannot compile scoped packet filter.");
            try
            {
                if (Function<SetFilter>("pcap_setfilter")(handle, ref filter) != 0) throw new IOException("Cannot apply packet filter.");
            }
            finally { Function<FreeFilter>("pcap_freecode")(ref filter); }
            if (Function<NonBlock>("pcap_setnonblock")(handle, 1, error) != 0) throw new IOException("Cannot set bounded reads.");
        }
        catch
        {
            if (handle != IntPtr.Zero) Function<Close>("pcap_close")(handle);
            NativeLibrary.Free(library); library = handle = IntPtr.Zero;
            throw;
        }
    }

    private static void VerifyLibrary(string path, string expected)
    {
        using var file = File.OpenRead(path);
        if (Convert.ToHexString(SHA256.HashData(file)) != expected)
            throw new IOException("Npcap version changed; signature review and re-pinning required.");
    }

    private T Function<T>(string name) where T : Delegate => Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(library, name));

    public byte[]? Poll()
    {
        ObjectDisposedException.ThrowIf(handle == IntPtr.Zero, this);
        var result = next(handle, out var header, out var data);
        if (result == 0) return null;
        if (result != 1 || header == IntPtr.Zero || data == IntPtr.Zero) throw new IOException("Packet read failed.");
        var h = Marshal.PtrToStructure<PacketHeader>(header);
        if (h.Captured != h.Length || h.Captured is < 18 or > 65535) throw new IOException("Incomplete packet.");
        var frame = new byte[h.Captured]; Marshal.Copy(data, frame, 0, frame.Length);
        if (!FrameScope.Incoming(frame, local)) throw new IOException("Packet filter scope violation.");
        return frame;
    }

    public void Send(byte[] frame)
    {
        ObjectDisposedException.ThrowIf(handle == IntPtr.Zero, this);
        if (!allowSend) throw new InvalidOperationException("This handle is passive-only.");
        if (!FrameScope.Outgoing(frame, local)) throw new InvalidDataException("Transmit scope violation.");
        if (send(handle, frame, frame.Length) != 0) throw new IOException("Packet send failed.");
    }

    public void Dispose()
    {
        if (handle != IntPtr.Zero) { close(handle); handle = IntPtr.Zero; }
        if (library != IntPtr.Zero) { NativeLibrary.Free(library); library = IntPtr.Zero; }
    }

    [StructLayout(LayoutKind.Sequential)] private struct BpfProgram { public uint Length; public IntPtr Instructions; }
    [StructLayout(LayoutKind.Sequential)] private struct PacketHeader { public int Seconds, Micros; public uint Captured, Length; }
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr LoadLibraryExW(string path, IntPtr reserved, uint flags);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate IntPtr LibraryVersion();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl, CharSet = CharSet.Ansi)] private delegate IntPtr Open(string name, int snap, int promisc, int timeout, StringBuilder error);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate void Close(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate int DataLink(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl, CharSet = CharSet.Ansi)] private delegate int Compile(IntPtr p, ref BpfProgram code, string expression, int optimize, uint mask);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate int SetFilter(IntPtr p, ref BpfProgram code);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate void FreeFilter(ref BpfProgram code);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl, CharSet = CharSet.Ansi)] private delegate int NonBlock(IntPtr p, int value, StringBuilder error);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate int Next(IntPtr p, out IntPtr header, out IntPtr data);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate int SendPacket(IntPtr p, byte[] data, int length);
}
