"""Just enough of the DNS wire format: read a question, build a block answer, cap TTLs."""
import socket
import struct


class BadPacket(ValueError):
    pass


_LDH = frozenset(b"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_*")


def parse_question(pkt):
    """Return (name, qtype, end_offset_of_question). Raises BadPacket unless this is a plain one-question query."""
    if len(pkt) < 17:
        raise BadPacket("short")
    flags, qd = struct.unpack("!HH", pkt[2:6])
    if flags & 0x8000 or (flags >> 11) & 0xF or qd != 1:
        raise BadPacket("not a standard query")
    i, labels = 12, []
    while True:
        if i >= len(pkt):
            raise BadPacket("truncated name")
        n = pkt[i]
        if n == 0:
            break
        if n > 63 or i + 1 + n > len(pkt):
            raise BadPacket("bad label")
        label = pkt[i + 1:i + 1 + n]
        if not _LDH.issuperset(label):
            raise BadPacket("odd characters")
        labels.append(label.decode().lower())
        i += n + 1
        if i > 270:
            raise BadPacket("name too long")
    if i + 5 > len(pkt):
        raise BadPacket("truncated question")
    return ".".join(labels), struct.unpack("!H", pkt[i + 1:i + 3])[0], i + 5


def formerr(pkt):
    """Minimal FORMERR reply for a packet we could not parse (keeps the id when there is one)."""
    return (pkt[:2] if len(pkt) >= 2 else b"\x00\x00") + b"\x81\x01\x00\x00\x00\x00\x00\x00\x00\x00"


def truncated_reply(reply):
    """Header and question only, with the TC bit set: the client then asks again over TCP."""
    try:
        _, _, end = parse_question(b"\x00\x00" + b"\x00\x00" + reply[4:])
    except BadPacket:
        end = 12
    return reply[:2] + bytes([reply[2] | 0x82, reply[3]]) + b"\x00\x01\x00\x00\x00\x00\x00\x00" + reply[12:end]


def skip_name(b, i):
    while True:
        n = b[i]
        if n == 0:
            return i + 1
        if n & 0xC0 == 0xC0:
            return i + 2
        i += n + 1


def blocked_reply(pkt, qtype, end):
    """Answer 0.0.0.0 for A queries and an empty answer for everything else."""
    rd = pkt[2] & 0x01          # echo the client's recursion-desired bit
    resp = pkt[:2] + bytes([0x80 | rd, 0x80]) + pkt[4:6] + (b"\x00\x01" if qtype == 1 else b"\x00\x00") + b"\x00\x00\x00\x00" + pkt[12:end]
    if qtype == 1:
        resp += b"\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04\x00\x00\x00\x00"
    return resp


def process_reply(resp, maxttl):
    """Cap answer TTLs (clients re-ask more often) and return (reply, [A-record ips])."""
    ips = []
    try:
        b = bytearray(resp)
        qd, an = struct.unpack("!HH", b[4:8])
        i = 12
        for _ in range(qd):
            i = skip_name(b, i) + 4
        for _ in range(an):
            i = skip_name(b, i)
            typ, _cls, ttl, rdlen = struct.unpack("!HHIH", b[i:i + 10])
            if maxttl and ttl > maxttl:
                b[i + 4:i + 8] = struct.pack("!I", maxttl)
            if typ == 1 and rdlen == 4:
                ips.append(socket.inet_ntoa(bytes(b[i + 10:i + 14])))
            i += 10 + rdlen
        return bytes(b), ips
    except Exception:
        return resp, ips


def build_query(name, qtype=1, txid=0x1234):
    """Build a query packet (used by tests and the self check)."""
    q = b"".join(bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\x00"
    return struct.pack("!HHHHHH", txid, 0x0100, 1, 0, 0, 0) + q + struct.pack("!HH", qtype, 1)
