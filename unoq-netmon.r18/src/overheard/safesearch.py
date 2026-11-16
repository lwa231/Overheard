"""Force the search engines' own SafeSearch by answering their hostnames with the providers' SafeSearch addresses
(the providers publish these names for exactly this purpose). Browsers that use their own encrypted DNS bypass it."""
import re
import struct

SEARCH = {
    "www.google.com": "forcesafesearch.google.com",
    "google.com": "forcesafesearch.google.com",
    "www.bing.com": "strict.bing.com",
    "bing.com": "strict.bing.com",
    "duckduckgo.com": "safe.duckduckgo.com",
    "www.duckduckgo.com": "safe.duckduckgo.com",
}
GOOGLE = re.compile(r"^(www\.)?google\.(com|co\.[a-z]{2}|com\.[a-z]{2}|[a-z]{2})$")      # every country edition of Google search


def target(name):
    n = name.lower().rstrip(".")
    if GOOGLE.match(n):
        return "forcesafesearch.google.com"
    return SEARCH.get(n)


def _enc(name):
    return b"".join(bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\x00"


def build_reply(pkt, qend, qtype, tgt, ips):
    """CNAME to the SafeSearch name plus its addresses. AAAA and HTTPS get an empty answer so clients use IPv4."""
    rd = pkt[2] & 0x01
    question = pkt[12:qend]
    answers = b""
    if qtype == 1 and ips:
        answers += b"\xc0\x0c" + struct.pack("!HHIH", 5, 1, 60, len(_enc(tgt))) + _enc(tgt)
        for ip in ips:
            answers += _enc(tgt) + struct.pack("!HHIH", 1, 1, 60, 4) + bytes(int(x) for x in ip.split("."))
        count = 1 + len(ips)
    else:
        count = 0
        answers = b""
    return pkt[:2] + bytes([0x80 | rd, 0x80]) + struct.pack("!HHHH", 1, count, 0, 0) + question + answers
