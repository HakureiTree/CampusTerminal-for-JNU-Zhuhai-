// SPDX-License-Identifier: GPL-3.0-or-later
using System.Buffers.Binary;
using System.Security.Cryptography;
using System.Text;
using System.Net;

namespace CampusAuth;

internal sealed record Step(string Event, byte[]? Response = null);
internal enum Phase { WaitingIdentity, WaitingMd5, WaitingSuccess, Authenticated, Failed }
internal enum IdentityProfile { JnuZhuhai, LegacyToken }

// Pure protocol state: never touches a NIC, process, proxy, file or desktop.
internal sealed class Protocol : IDisposable
{
    private readonly byte[] local, username, password, ip, version;
    private readonly H3cCrypto crypto;
    private readonly IdentityProfile profile;
    private byte[]? server, token, lastRequest, lastResponse;
    private byte md5Identifier;
    private byte initialIdentifier;
    public Phase State { get; private set; } = Phase.WaitingIdentity;
    public bool HasVendorToken => token != null;
    public bool AddressBound { get; private set; }

    public Protocol(byte[] local, string username, byte[] password, byte[] ip, uint nonce, H3cCrypto crypto,
        IdentityProfile profile = IdentityProfile.JnuZhuhai, bool requireAddressBinding = false)
    {
        if (local.Length != 6 || (local[0] & 1) != 0 || local.All(b => b == 0) || ip.Length != 4)
            throw new ArgumentException("Invalid interface identity.");
        if (username.Length is < 1 or > 128 || username.Any(c => c < 33 || c > 126) ||
            password.Length is < 1 or > 128)
            throw new ArgumentException("Unsupported credential encoding or length.");
        this.local = local.ToArray(); this.username = Encoding.ASCII.GetBytes(username);
        this.password = password.ToArray(); this.ip = ip.ToArray(); this.crypto = crypto;
        this.profile = profile;
        AddressBound = !requireAddressBinding;
        version = H3cCrypto.EncodedVersion(nonce);
    }

    public byte[] Start() => Envelope(Enumerable.Repeat((byte)255, 6).ToArray(), 1, []);

    public void BindAddress(byte[] address)
    {
        if (AddressBound || State != Phase.Authenticated || address.Length != 4 ||
            !TrialAddressGate.UsableIpv4(new IPAddress(address).ToString()))
            throw new InvalidOperationException("Address binding is not valid for this session.");
        address.CopyTo(ip, 0);
        AddressBound = true;
    }

    public byte[]? CloseSession()
    {
        if (State != Phase.Authenticated || server == null) return null;
        State = Phase.Failed;
        return Envelope(server, 2, []);
    }

    private byte[] CampusHeartbeatPayload()
    {
        var address = Encoding.ASCII.GetBytes(new IPAddress(ip).ToString());
        return Join([0x15, 0x14, checked((byte)address.Length)], address, [6, 7], version, [32, 32], username);
    }

    // The recorded client sends these every 30 seconds with the initial Identity id,
    // separately from responses that echo fresh server request ids.
    public Step PeriodicHeartbeat()
    {
        if (State != Phase.Authenticated || profile != IdentityProfile.JnuZhuhai || !AddressBound)
            return new("HeartbeatNotReady");
        return new("PeriodicHeartbeatPrepared", IdentityEnvelope(initialIdentifier, CampusHeartbeatPayload()));
    }

    private byte[] IdentityEnvelope(byte id, byte[] payload)
    {
        var eap = new byte[5 + payload.Length];
        eap[0] = 2; eap[1] = id; eap[4] = 1;
        BinaryPrimitives.WriteUInt16BigEndian(eap.AsSpan(2), checked((ushort)eap.Length));
        payload.CopyTo(eap, 5);
        return Envelope(server!, 0, eap);
    }

    public Step Receive(byte[] frame)
    {
        if (State == Phase.Failed) return new("SessionStopped");
        if (frame.Length < 14) return new("IgnoredShortEthernet");
        if (!frame.AsSpan(0, 6).SequenceEqual(local) || frame[12] != 0x88 || frame[13] != 0x8e)
            return new("IgnoredOtherTraffic");
        if (frame.AsSpan(6, 6).SequenceEqual(local) || (frame[6] & 1) != 0 ||
            frame.AsSpan(6, 6).SequenceEqual(new byte[6])) return new("IgnoredInvalidSource");
        if (server != null && !frame.AsSpan(6, 6).SequenceEqual(server)) return Fail("ServerIdentityChanged");
        if (frame.Length < 22 || frame[14] != 1 || frame[15] != 0) return Fail("UnsupportedEapol");
        var length = BinaryPrimitives.ReadUInt16BigEndian(frame.AsSpan(16));
        if (length < 4 || length > frame.Length - 18 ||
            length != BinaryPrimitives.ReadUInt16BigEndian(frame.AsSpan(20))) return Fail("MalformedEapLength");
        var eap = frame.AsSpan(18, length).ToArray();
        byte code = eap[0], id = eap[1];
        if (server == null)
        {
            if (code != 1 || length < 5 || eap[4] != 1) return new("IgnoredBeforeIdentity");
            server = frame.AsSpan(6, 6).ToArray();
        }
        if (code == 4)
        {
            if (State == Phase.WaitingMd5 && id != initialIdentifier) return new("IgnoredStaleFailure");
            if (State == Phase.WaitingSuccess && id != md5Identifier) return new("IgnoredStaleFailure");
            return Fail("AuthenticationRejected");
        }
        if (code == 3)
        {
            if (length != 4 || State != Phase.WaitingSuccess || id != md5Identifier)
                return Fail("UnexpectedSuccess");
            State = Phase.Authenticated;
            return new("EapSuccessNotConnectivityVerified");
        }
        if (code == 10)
        {
            if (State is not (Phase.WaitingSuccess or Phase.Authenticated)) return Fail("UnexpectedVendorData");
            if (length >= 9 && eap[7] == 0x2b && eap[8] == 0x35)
            {
                if (length < 41) return Fail("TruncatedVendorChallenge");
                try { token = crypto.ChallengeToken(eap.AsSpan(9, 32)); }
                catch (InvalidDataException) { return Fail("UnsupportedVendorChallenge"); }
                return new("VendorTokenComputed");
            }
            return new("UninterpretedVendorNotice");
        }
        if (code != 1 || length < 5) return Fail("UnsupportedEapCode");
        if (lastRequest != null && eap.SequenceEqual(lastRequest))
            return new("RetransmittedResponse", lastResponse!.ToArray());
        byte[] payload;
        switch (eap[4])
        {
            case 1:
                if (State == Phase.WaitingIdentity)
                {
                    initialIdentifier = id;
                    payload = Join([6, 7], version, [32, 32], username);
                    State = Phase.WaitingMd5;
                }
                else if (State == Phase.Authenticated && profile == IdentityProfile.JnuZhuhai)
                {
                    if (!AddressBound) return new("AwaitingIpv4");
                    payload = CampusHeartbeatPayload();
                }
                else if (State == Phase.Authenticated && token != null)
                    payload = Join([0x16, 0x20], token, [0x15, 4], ip, [6, 7], version, [32, 32], username);
                else return Fail("IdentityOutOfSequenceOrMissingToken");
                break;
            case 4:
                if (State != Phase.WaitingMd5 || length != 22 || eap[5] != 16)
                    return Fail("InvalidMd5Challenge");
                var digestInput = Join([id], password, eap.AsSpan(6, 16).ToArray());
                var digest = MD5.HashData(digestInput);
                CryptographicOperations.ZeroMemory(digestInput);
                payload = Join([16], digest, username);
                md5Identifier = id;
                State = Phase.WaitingSuccess;
                break;
            case 7: return Fail("PlaintextPasswordMethodRefused");
            default: return Fail("UnsupportedEapMethod");
        }
        var response = new byte[5 + payload.Length];
        response[0] = 2; response[1] = id; response[4] = eap[4];
        BinaryPrimitives.WriteUInt16BigEndian(response.AsSpan(2), checked((ushort)response.Length));
        payload.CopyTo(response, 5);
        lastRequest = eap;
        lastResponse = Envelope(server, 0, response);
        return new(eap[4] == 4 ? "Md5ResponsePrepared" : "IdentityResponsePrepared", lastResponse.ToArray());
    }

    private Step Fail(string reason) { State = Phase.Failed; return new(reason); }
    private byte[] Envelope(byte[] destination, byte type, byte[] payload)
    {
        var result = new byte[18 + payload.Length];
        destination.CopyTo(result, 0); local.CopyTo(result, 6);
        result[12] = 0x88; result[13] = 0x8e; result[14] = 1; result[15] = type;
        BinaryPrimitives.WriteUInt16BigEndian(result.AsSpan(16), checked((ushort)payload.Length));
        payload.CopyTo(result, 18);
        return result;
    }
    private static byte[] Join(params byte[][] arrays) => arrays.SelectMany(a => a).ToArray();
    public void Dispose()
    {
        CryptographicOperations.ZeroMemory(password);
        if (token != null) CryptographicOperations.ZeroMemory(token);
        if (lastResponse != null) CryptographicOperations.ZeroMemory(lastResponse);
    }
}
