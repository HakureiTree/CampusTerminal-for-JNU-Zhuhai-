// SPDX-License-Identifier: GPL-3.0-or-later
// Adapted from Besfim/inode-njit; see ../../THIRD-PARTY.md.
using System.Buffers.Binary;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;

namespace CampusAuth;

internal interface IChallengeDictionary
{
    byte[] Lookup(uint key, int offset, int length);
}

internal sealed class EmbeddedDictionary : IChallengeDictionary
{
    private readonly Dictionary<uint, byte[]> dictionary = new();

    public EmbeddedDictionary()
    {
        using var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("h3c_dict.h")!;
        using var memory = new MemoryStream();
        stream.CopyTo(memory);
        var bytes = memory.ToArray();
        if (Convert.ToHexString(SHA256.HashData(bytes)) !=
            "C5EDE6A8B3CC3C5C53147900512911F583D6439F451B51F3F0421E353455C4E1")
            throw new InvalidDataException("Protocol dictionary integrity check failed.");
        foreach (Match entry in Regex.Matches(Encoding.ASCII.GetString(bytes),
                     @"const unsigned char x([0-9A-F]{8})\[\] = \{([^}]+)\};"))
        {
            dictionary.Add(Convert.ToUInt32(entry.Groups[1].Value, 16),
                Regex.Matches(entry.Groups[2].Value, @"0x([0-9A-Fa-f]{2})")
                    .Select(m => Convert.ToByte(m.Groups[1].Value, 16)).ToArray());
        }
        if (dictionary.Count != 40) throw new InvalidDataException("Unexpected dictionary shape.");
    }

    public byte[] Lookup(uint key, int offset, int length)
    {
        if (!dictionary.TryGetValue(key, out var data) || offset < 0 || length < 0 || offset + length > data.Length)
            throw new InvalidDataException("Unsupported H3C dictionary challenge; live use blocked.");
        return data.AsSpan(offset, length).ToArray();
    }
}

internal sealed class H3cCrypto
{
    private readonly IChallengeDictionary dictionary;
    private static readonly byte[] Iv = Encoding.ASCII.GetBytes("a@4de%#1asdfsd24");
    public H3cCrypto(IChallengeDictionary? dictionary = null) => this.dictionary = dictionary ?? new EmbeddedDictionary();
    private byte[] Signature(ReadOnlySpan<byte> descriptor) => dictionary.Lookup(
        BinaryPrimitives.ReadUInt32BigEndian(descriptor), descriptor[4], descriptor[5]);

    public byte[] ChallengeToken(ReadOnlySpan<byte> challenge)
    {
        if (challenge.Length != 32) throw new InvalidDataException("Invalid H3C challenge length.");
        using var aes = Aes.Create();
        aes.Key = Convert.FromHexString("ECD44F7BC6DD7DDE2B7B51AB4A6F5A22");
        var first = aes.DecryptCbc(challenge, Iv, PaddingMode.None);
        var sig1 = Signature(first.AsSpan(0, 6));
        aes.Key = MD5.HashData(sig1);
        var second = aes.DecryptCbc(first.AsSpan(16, 16), Iv, PaddingMode.None);
        var sig2 = Signature(second.AsSpan(10, 6));
        second.CopyTo(first, 16);
        var signatures = sig1.Concat(sig2).ToArray();
        signatures.AsSpan(0, Math.Min(32, signatures.Length)).CopyTo(first);
        var digest = MD5.HashData(first);
        return digest.Concat(MD5.HashData(digest)).ToArray();
    }

    public static byte[] EncodedVersion(uint nonce)
    {
        var version = new byte[20];
        Encoding.ASCII.GetBytes("CH\u0011V7.30-0536").CopyTo(version, 0);
        Xor(version.AsSpan(0, 16), Encoding.ASCII.GetBytes(nonce.ToString("x8")));
        BinaryPrimitives.WriteUInt32BigEndian(version.AsSpan(16), nonce);
        Xor(version, Encoding.ASCII.GetBytes("Oly5D62FaE94W7"));
        return Encoding.ASCII.GetBytes(Convert.ToBase64String(version));
    }

    public static uint DecodeVerifiedVersion(ReadOnlySpan<byte> encoded)
    {
        var data = Convert.FromBase64String(Encoding.ASCII.GetString(encoded));
        if (data.Length != 20) throw new InvalidDataException("Unexpected version field size.");
        Xor(data, Encoding.ASCII.GetBytes("Oly5D62FaE94W7"));
        var nonce = BinaryPrimitives.ReadUInt32BigEndian(data.AsSpan(16));
        if (!encoded.SequenceEqual(EncodedVersion(nonce)))
            throw new InvalidDataException("Client version does not match the verified campus profile.");
        return nonce;
    }

    private static void Xor(Span<byte> value, ReadOnlySpan<byte> key)
    {
        for (var i = 0; i < value.Length; i++) value[i] ^= key[i % key.Length];
        for (var i = 0; i < value.Length; i++) value[value.Length - 1 - i] ^= key[i % key.Length];
    }
}
