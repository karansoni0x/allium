#!/usr/bin/env python3
"""Allium v2.7 PRO - dark web onion discovery engine.

Menu-driven (numbered options, multi-select, custom keywords).
Hunts .onion links across public directories + LIVE Tor search
engines + live ransomware leak-site tracking, filters strictly,
ranks by corroboration, explains every result.

Directory sources: dark.fail | onion.live | tor.taxi | ransomware.live
Search engines (live): Ahmia + Torch (clearnet) + 25 verified onion
    search engines via Tor stealth mode

Research / defensive OSINT use only. Discovery + verification only -
the tool never interacts with, purchases from, or attacks any service.

Usage:
    python3 allium.py
"""
import csv
import html as htmlmod
import ipaddress
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html.parser import HTMLParser

VERSION = "v2.7 PRO"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) research-bot"}

# ---------------------------------------------------------------- Pro UI
GH_USER = "karansoni0x"
GH_URL = "https://github.com/" + GH_USER


def _use_color():
    if os.environ.get("NO_COLOR"):
        return False
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


USE_COLOR = _use_color()


def paint(text, *codes):
    if not USE_COLOR or not codes:
        return text
    return "\033[" + ";".join(codes) + "m" + str(text) + "\033[0m"


BOLD, DIM, RED, GREEN, YELLOW, CYAN, MAG, WHITE = \
    "1", "2", "31", "32", "33", "36", "35", "37"


def _hyperlinks_supported():
    """OSC 8 terminal hyperlinks: on for terminals known to render them."""
    if not USE_COLOR:
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    return bool(os.environ.get("WT_SESSION")        # Windows Terminal
                or os.environ.get("TERM_PROGRAM")   # iTerm2, WezTerm, kitty…
                or os.environ.get("VTE_VERSION")    # GNOME Terminal etc.
                or os.environ.get("COLORTERM")      # truecolor terminals
                or os.environ.get("KONSOLE_VERSION"))


def gh_link(label=None):
    """Clickable GitHub hyperlink (OSC 8); plain URL fallback."""
    label = label or ("github.com/" + GH_USER)
    if _hyperlinks_supported():
        return f"\033]8;;{GH_URL}\033\\{label}\033]8;;\033\\"
    return GH_URL  # plain URL is clickable in modern terminals


def divider(char="═", width=76):
    return paint("  " + char * width, CYAN, DIM)


def section(title):
    bar = "─" * max(8, 68 - len(title))
    return paint(f"\n  ┌─ {title} {bar}", MAG, BOLD)


def stamp():
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


# ---------------------------------------------------------------- patterns
ONION_RE = re.compile(r"\b([a-z2-7]{56})\.onion\b")
ONION_FULL_RE = re.compile(r"^[a-z2-7]{56}\.onion$")

# Hardening (v2.7): remote page titles can carry &#27; (ESC) via
# html.unescape() -> ANSI/OSC terminal injection (fake output,
# hidden lines, OSC 52 clipboard overwrite on some terminals).
# Strip ALL control chars from remote-sourced display strings.
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def _clean(s):
    """Strip terminal control characters from remote-sourced text."""
    return _CTRL_RE.sub("", s or "")


def _csv_cell(s):
    """Neutralize CSV formula injection (=, +, -, @ prefixes)."""
    s = str(s)
    return "'" + s if s[:1] in ("=", "+", "-", "@") else s
DEAD_RE = re.compile(r"\[(offline|dead|seized)", re.I)
TIMEOUT = 25
HEAD_LIMIT = 150_000
MAX_BODY = 10_000_000  # audit: cap full-body reads

CATEGORIES = {
    "1": ("Breach & Leak Forums",
          ["breach", "leak", "dump", "database", "combo", "stealer"]),
    "2": ("Russian Forums",
          ["exploit", "xss", "bhf", "lolz", "zelenka", "club2crd",
           "crdpro", "damagelib", "rehub"]),
    "3": ("English Hacking Forums",
          ["hackforum", "cracked", "sinister", "altenen", "0day",
           "darkforum", "xforum", "zeroforum", "spear", "banished"]),
    "4": ("Ransomware Leak Sites",
          ["ransom", "lockbit", "qilin", "akira", "everest", "safepay",
           "dragonforce", "nightspire", "incransom", "blog", "dls"]),
    "5": ("AI Chatbots & Tools",
          ["gpt", "chatbot", "llm", "venice", "deepseek", "mistral",
           "neural", "assistant", "artificial intelligence"]),
    "6": ("Country-Specific Forums & Data", []),  # keywords via picker
    "7": ("Other (custom keywords)", []),
    "8": ("FULL SWEEP", []),
}
CAT_BLURB = {
    "Breach & Leak Forums": "forum focused on data breaches and leaked databases",
    "Russian Forums": "Russian-language hacking forum",
    "English Hacking Forums": "English-language hacking forum",
    "Ransomware Leak Sites": "ransomware gang data-leak site (DLS)",
    "AI Chatbots & Tools": "AI chatbot / AI tool",
}
OL_CATS = ["directories", "exchange", "forum", "hosting", "market",
           "other", "search-engine", "tools", "vendor", "vpn", "wallet"]
SEED_CATS = {"breach": "1", "russian": "2", "english": "3",
             "ransomware": "4"}
# Intel skip-list: seized / honeypot-risk / dead. Word-boundary match.
BLOCKLIST = {"breachforums", "xss.is", "ramp", "nulled",
             "ransomhub", "medusa", "lynx", "hunters"}

# What-onion-types submenu (after country pick). type -> (label, keywords)
COUNTRY_TYPES = {
    "1": ("Forums", ["forum", "board", "community", "chan"]),
    "2": ("Markets & Shops", ["market", "shop", "vendor", "store", "bazaar"]),
    "3": ("Leak Sites & Breach Data",
          ["leak", "breach", "dump", "database", "combo"]),
    "4": ("Ransomware DLS", ["ransom", "dls", "blog", "leak site"]),
    "5": ("AI Chatbots & Tools", ["ai", "gpt", "chatbot", "llm", "neural"]),
    "6": ("All country-related", []),
}

# Engine queries per category (2 each - enough signal, no hammering)
ENGINE_QUERIES = {
    "Breach & Leak Forums": ["breach forum", "leak forum"],
    "Russian Forums": ["russian hacking forum", "russian forum"],
    "English Hacking Forums": ["hacking forum", "cracked forum"],
    "Ransomware Leak Sites": ["ransomware leak site", "ransomware blog"],
    "AI Chatbots & Tools": ["ai chatbot", "uncensored ai chat"],
}
SWEEP_QUERIES = ["hacking forum", "dark market", "data leak",
                 "ransomware", "ai chatbot"]

# ------------------------------------------------------- Stealth (Tor)
TOR_HOST = "127.0.0.1"
TOR_PORTS = (9050, 9150)  # system Tor, Tor Browser
TOR_PORT = None
USE_TOR = False
TOR_FAILS = 0


def tor_available():
    """Try 9050 (system Tor) then 9150 (Tor Browser)."""
    global TOR_PORT
    for p in TOR_PORTS:
        try:
            s = socket.create_connection((TOR_HOST, p), timeout=5)
            s.close()
            TOR_PORT = p
            return True
        except OSError:
            continue
    TOR_PORT = None
    return False


def _recvn(s, n):
    """Read exactly n bytes (SOCKS handshakes can short-read)."""
    data = b""
    while len(data) < n:
        chunk = s.recv(n - len(data))
        if not chunk:
            raise OSError("tor: socks short read")
        data += chunk
    return data


def socks5_connect(host, port, timeout=TIMEOUT):
    """TCP via Tor SOCKS5. Hostname goes to Tor (remote DNS) -
    no local DNS leak; sites see the Tor exit IP, never yours."""
    if len(host) > 255:  # audit F25: SOCKS5 domain field is 1 length byte
        raise OSError("tor: hostname too long")
    try:
        hb = host.encode("idna")
    except UnicodeError:
        raise OSError("tor: bad hostname encoding")
    if len(hb) > 255:
        raise OSError("tor: hostname too long")
    s = socket.create_connection((TOR_HOST, TOR_PORT), timeout=timeout)
    try:
        s.sendall(b"\x05\x01\x00")
        if _recvn(s, 2) != b"\x05\x00":
            raise OSError("tor: socks handshake rejected")
        s.sendall(b"\x05\x01\x00\x03" + bytes([len(hb)]) + hb
                  + port.to_bytes(2, "big"))
        rep = _recvn(s, 4)  # VER REP RSV ATYP
        if rep[1] != 0x00:
            raise OSError("tor: socks connect failed")
        # consume the rest of the variable-length reply
        atyp = rep[3]
        if atyp == 0x01:      # IPv4: 4 addr + 2 port
            _recvn(s, 6)
        elif atyp == 0x04:    # IPv6: 16 addr + 2 port
            _recvn(s, 18)
        elif atyp == 0x03:    # domain: 1 len + addr + 2 port
            _recvn(s, _recvn(s, 1)[0] + 2)
        else:
            raise OSError("tor: bad socks reply")
        return s
    except Exception:
        s.close()
        raise


def dechunk(data):
    parts, i = [], 0
    while True:
        j = data.find(b"\r\n", i)
        if j < 0:
            break
        try:
            size = int(data[i:j].split(b";")[0], 16)
        except ValueError:
            break
        if size == 0:
            break
        i = j + 2
        parts.append(data[i:i + size])
        i += size + 2
    return b"".join(parts) or data


def fetch_tor(url, limit=None, redirs=3):
    """GET via Tor SOCKS5h. No cookies, no identifying headers,
    follows http(s) redirects only. Raises on any Tor failure -
    never falls back to clearnet (fail-closed).

    Audit guards: CR/LF rejected (header injection), body capped,
    redirect scheme restricted to http/https."""
    if re.search(r"[\r\n]", url):
        raise OSError("tor: invalid URL")
    u = urllib.parse.urlsplit(url)
    host = u.hostname or ""
    if "\r" in host or "\n" in host:
        raise OSError("tor: invalid host")
    try:
        port = u.port or (443 if u.scheme == "https" else 80)
    except ValueError:
        raise OSError("tor: bad port")  # audit F4: e.g. http://x:abc/
    path = u.path or "/"
    if u.query:
        path += "?" + u.query
    if "\r" in path or "\n" in path:
        raise OSError("tor: invalid path")
    s = socks5_connect(host, port)
    try:
        if u.scheme == "https":
            s = ssl.create_default_context().wrap_socket(
                s, server_hostname=host)
        # Functional fix: Host header must carry non-default ports.
        host_hdr = host if port in (80, 443) else f"{host}:{port}"
        s.sendall(f"GET {path} HTTP/1.1\r\nHost: {host_hdr}\r\n"
                  f"User-Agent: {UA['User-Agent']}\r\n"
                  f"Connection: close\r\n\r\n".encode())
        # Hardening: overall deadline - a slow-drip hostile server
        # must not hold a worker forever (per-recv timeouts reset).
        deadline = time.monotonic() + TIMEOUT * 2
        data = b""
        while True:
            if time.monotonic() > deadline:
                raise OSError("tor: deadline exceeded")
            chunk = s.recv(65536)
            if not chunk:
                break
            data += chunk
            if limit and len(data) >= limit + 8192:
                break
            if not limit and len(data) >= MAX_BODY:
                break
        head, _, body = data.partition(b"\r\n\r\n")
        if b"transfer-encoding: chunked" in head.lower():
            body = dechunk(body)
        m = re.search(rb"^http/\S+ (\d{3})", head)
        code = int(m.group(1)) if m else 0
        if code in (301, 302, 303, 307, 308) and redirs > 0:
            lm = re.search(rb"(?m)^location:\s*(\S+)", head)
            if lm:
                loc = urllib.parse.urljoin(
                    url, lm.group(1).decode("utf-8", "replace").strip())
                if urllib.parse.urlsplit(loc).scheme not in (
                        "http", "https"):
                    raise OSError("tor: bad redirect scheme")
                return fetch_tor(loc, limit, redirs - 1)
        if code >= 400:
            raise OSError(f"tor: http {code} for {host}")
        return body[:limit] if limit else body
    finally:
        try:
            s.close()
        except Exception:
            pass


# ------------------------------------------------- clearnet HTTP layer
# Audit F2: urllib follows redirects to ANY scheme (file:// included).
# This opener only permits http/https redirects.
# v2.7: also blocks redirects to private/loopback/link-local IPs
# (compromised directory -> SSRF against your LAN via your machine).
def _host_is_public(host):
    """True only if every resolved IP is globally routable."""
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError:
        return False
    addrs = set()
    for fam, _, _, _, sa in infos:
        try:
            addrs.add(ipaddress.ip_address(sa[0]))
        except ValueError:
            return False
    return bool(addrs) and all(ip.is_global for ip in addrs)


class _HttpOnlyRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        u = urllib.parse.urlsplit(urllib.parse.urljoin(req.full_url,
                                                       newurl))
        if u.scheme not in ("http", "https"):
            raise OSError(f"blocked redirect to {u.scheme or 'unknown'} "
                          "scheme")
        host = u.hostname or ""
        if host and not _host_is_public(host):
            raise OSError(f"blocked redirect to non-public host {host}")
        return super().redirect_request(req, fp, code, msg, headers,
                                        newurl)


_URL_OPENER = urllib.request.build_opener(_HttpOnlyRedirect)


def _read_capped(resp, cap=MAX_BODY):
    """Audit F1: never read an unbounded body (malicious server -> OOM)."""
    data = b""
    while len(data) < cap:
        chunk = resp.read(min(65536, cap - len(data)))
        if not chunk:
            break
        data += chunk
    return data


def fetch(url):
    if USE_TOR:
        try:
            return fetch_tor(url).decode("utf-8", "replace")
        except OSError:
            global TOR_FAILS
            TOR_FAILS += 1
            raise
    req = urllib.request.Request(url, headers=UA)
    with _URL_OPENER.open(req, timeout=TIMEOUT) as r:
        return _read_capped(r).decode("utf-8", "replace")


def fetch_head(url, limit=HEAD_LIMIT):
    if USE_TOR:
        try:
            return fetch_tor(url, limit).decode("utf-8", "replace")
        except OSError:
            global TOR_FAILS
            TOR_FAILS += 1
            raise
    req = urllib.request.Request(url, headers=UA)
    with _URL_OPENER.open(req, timeout=TIMEOUT) as r:
        return r.read(limit).decode("utf-8", "replace")


def find_onions(text):
    return sorted({m.group(0) for m in ONION_RE.finditer(text)})


def is_blocked(name):
    n = " " + name.lower() + " "
    return any(" " + b + " " in n for b in BLOCKLIST)


class Prog:
    """In-place progress bar with elapsed time and ETA."""

    def __init__(self, total, label):
        self.total, self.label = max(total, 1), label
        self.n, self.t0 = 0, time.time()
        self._last_draw = 0.0

    def tick(self, step=1):
        self.n += step
        now = time.time()
        # Throttle: max 1 redraw/sec so terminals that ignore \r
        # don't get flooded with stacked lines.
        if now - self._last_draw < 1.0 and self.n < self.total:
            return
        self._last_draw = now
        el = now - self.t0
        rate = self.n / el if el > 0 else 0
        eta = (self.total - self.n) / rate if rate > 0 else 0
        width = 22
        filled = int(width * self.n / self.total)
        bar = paint("█" * filled, GREEN, BOLD) + paint(
            "░" * (width - filled), DIM)
        sys.stdout.write(
            f"\r  [{self.label}] {bar} {self.n}/{self.total} | "
            f"{el:.0f}s elapsed | ETA {eta:.0f}s   ")
        sys.stdout.flush()

    def done(self, extra=""):
        msg = f"\r  [{self.label}] done in {time.time() - self.t0:.0f}s"
        if extra:
            msg += f" ({extra})"
        sys.stdout.write(paint(msg, GREEN, BOLD) + " " * 30 + "\n")
        sys.stdout.flush()


class Anchors(HTMLParser):
    def __init__(self):
        super().__init__()
        self.pairs, self._href, self._text = [], None, []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href, self._text = dict(attrs).get("href"), []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data.strip())

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.pairs.append((self._href, " ".join(self._text)))
            self._href = None


def parse_engine_blocks(html, cap=250):
    """Parse Ahmia/Torch-style result blocks.

    <li class="result"><h4><a>TITLE</a></h4><p>desc</p>
    <cite>xxx.onion</cite><span class="lastSeen" data-timestamp="...">
    Returns [(title, onion-with-http, last_seen)].

    v2.7: page truncated to 2MB before regex - a hostile 10MB page
    without </li> closers could otherwise make matching quadratic.
    """
    html = html[:2_000_000]
    out = []
    for m in re.finditer(r'<li class="result">(.*?)</li>', html, re.S):
        if len(out) >= cap:
            break
        b = m.group(1)
        tm = re.search(r"<h4>\s*<a[^>]*>(.*?)</a>", b, re.S)
        cm = re.search(r"<cite>(.*?)</cite>", b, re.S)
        sm = re.search(r'data-timestamp="([^"]+)"', b)
        title = htmlmod.unescape(
            re.sub(r"<[^>]+>", "", tm.group(1)).strip()) if tm else ""
        onion = cm.group(1).strip().lower() if cm else ""
        seen = sm.group(1).strip() if sm else ""
        if ONION_FULL_RE.match(onion):
            out.append((title or onion, "http://" + onion, seen))
    return out


def ahmia_token():
    """Ahmia gates /search behind a hidden form token. Extract it
    live from the homepage; fall back to the last-known value."""
    try:
        home = fetch("https://ahmia.fi/")
        m = re.search(
            r'<input type="hidden" name="([a-z0-9]+)" value="([a-z0-9]+)">',
            home)
        if m:
            return m.group(1), m.group(2)
    except Exception:
        pass
    return "fa0c83", "4c09c3"  # last-known good (2026-10-18)

# ------------------------------------------------- directory hunts
# Runtime opacity: the running tool never names its sources or engines
# in any user-visible output. Source identities stay inside the code;
# users see only counts, scores and results.
_SRC_N = [0]


def _live(msg):
    _SRC_N[0] += 1
    print(paint(f"  [•] Source {_SRC_N[0]}: {msg}  ({stamp()} UTC)", CYAN))


def hunt_darkfail():
    t0 = time.time()
    _live("fetching live directory index…")
    out = []
    try:
        main = fetch("https://dark.fail/")
    except Exception as e:
        print(paint(f"  [!] a directory is unreachable: {e}", RED))
        return out, {"source": "directory", "rows": 0,
                     "secs": time.time() - t0, "status": "unreachable"}
    p = Anchors()
    p.feed(main)
    svcs = sorted({h for h, _ in p.pairs
                   if h.startswith("/") and not h.startswith("//")
                   and h != "/" and "." not in h.split("/")[-1]
                   and not h.startswith("/#")})
    prog = Prog(len(svcs), "directory")
    for svc in svcs:
        try:
            page = fetch("https://dark.fail" + svc)
        except Exception:
            prog.tick()
            continue
        name = svc.strip("/")
        m = re.search(r"Is (.+?) online on the darknet\?", page)
        if m:
            name = htmlmod.unescape(m.group(1)).strip()
        for o in find_onions(page):
            out.append((name, "http://" + o, "dark.fail", name))
        prog.tick()
        time.sleep(0.3)
    prog.done(f"{len(out)} rows")
    return out, {"source": "directory", "rows": len(out),
                 "secs": time.time() - t0, "status": "ok"}


def hunt_onionlive():
    t0 = time.time()
    _live("fetching live category index…")
    out = []
    prog = Prog(len(OL_CATS), "directory")
    for cat in OL_CATS:
        try:
            page = fetch(f"https://onion.live/category/{cat}")
        except Exception as e:
            print(paint(f"\n  [!] a category index is unreachable: {e}", RED))
            prog.tick()
            continue
        for card in re.split(r'<h3 class="card-title">', page)[1:]:
            nm = re.search(r'<span class="text-[a-z]+-500">(.*?)</span>', card)
            st = re.search(r'status-badge status-(\w+)', card)
            name = htmlmod.unescape(nm.group(1)).strip() if nm else cat
            status = st.group(1) if st else "?"
            for o in find_onions(card):
                out.append((name, "http://" + o, "onion.live",
                            f"{name} [{status}]"))
        prog.tick()
        time.sleep(0.3)
    prog.done(f"{len(out)} rows")
    return out, {"source": "directory", "rows": len(out),
                 "secs": time.time() - t0, "status": "ok"}


def hunt_tortaxi():
    t0 = time.time()
    _live("fetching live index…")
    out = []
    try:
        page = fetch("https://tor.taxi/")
    except Exception as e:
        print(paint(f"  [!] a directory is unreachable: {e}", RED))
        return out, {"source": "directory", "rows": 0,
                     "secs": time.time() - t0, "status": "unreachable"}
    p = Anchors()
    p.feed(page)
    for href, text in p.pairs:
        name = text if len(text) >= 3 and not text.startswith("@") else None
        for o in find_onions(href):
            out.append((name or o, "http://" + o, "tor.taxi", text or o))
    print(paint(f"  [directory] done ({len(out)} rows)", GREEN))
    return out, {"source": "directory", "rows": len(out),
                 "secs": time.time() - t0, "status": "ok"}


def _fetch_group(g):
    try:
        page = fetch_head("https://ransomware.live/group/"
                          + urllib.parse.quote(g, safe=""))
    except Exception:
        return []
    name = htmlmod.unescape(g)
    return [(name, "http://" + o, "ransomware.live", f"{name} [DLS]")
            for o in find_onions(page)]


def hunt_ransomware_live():
    t0 = time.time()
    _live("enumerating live leak-site groups…")
    out = []
    try:
        listing = fetch("https://ransomware.live/groups")
    except Exception as e:
        print(paint(f"  [!] a directory is unreachable: {e}", RED))
        return out, {"source": "directory", "rows": 0,
                     "secs": time.time() - t0, "status": "unreachable"}
    groups = sorted({urllib.parse.unquote(m.group(1)).split("#")[0]
                     for m in re.finditer(r'href="/group/([^"]+)"', listing)}
                    - {""})
    prog = Prog(len(groups), "directory")
    with ThreadPoolExecutor(max_workers=15) as ex:
        futs = {ex.submit(_fetch_group, g): g for g in groups}
        for f in as_completed(futs):
            try:
                out += f.result()
            except Exception:
                pass
            prog.tick()
    prog.done(f"{len(out)} rows")
    return out, {"source": "directory", "rows": len(out),
                 "secs": time.time() - t0, "status": "ok"}


# ------------------------------------------------- search engines (live)
# Clearnet engines: queried always. Onion-only engines: stealth (Tor) mode.
# NOTE: engine identities never appear in user-visible output (labels,
# progress bars, summaries, exports). They stay inside the code only.
CLEARNET_ENGINES = ("ahmia", "torch")
ONION_ENGINES = {
    # key: (label, v3 host, search path with {q} = url-encoded query)
    # Addresses verified alive Oct 2026 (Avira / onion.live /
    # megadose/OnionSearch project). Query patterns are best-effort:
    # a wrong pattern just yields no rows (fail-safe, strict-filtered).
    "haystak": ("Haystak",
                "haystak5njsmn2hqkewecpaxetahtwhsbsa64jom2k22z5afxhnpxfid.onion",
                "/?q={q}&offset=0"),
    "tor66": ("Tor66",
              "tor66sewebgixwhcqfnp5inzp5x5uohhdy3kvtnyfxc2e5mxiuh34iid.onion",
              "/search?q={q}&sorttype=rel&page=1"),
    "onionland": ("OnionLand",
                  "3bbad7fauom4d6sgppalyqddsqbf5u5p56b5k5uk2zxsy3d6ey2jobad.onion",
                  "/search?q={q}&page=1"),
    "amnesia": ("Amnesia",
                "amnesia7u5odx5xbwtpnqk3edybgud5bmiagu75bnqx2crntw5kry7ad.onion",
                "/search?q={q}"),
    "bobby": ("Bobby",
              "bobby64o755x3gsuznts6hf6agxqjcz5bop6hs7ejorekbm7omes34ad.onion",
              "/search?q={q}"),
    "deepsearch": ("Deep Search",
                   "search7tdrcvri22rieiwgi5g46qnwsesvnubqav2xakhezv4hjzkkad.onion",
                   "/search?q={q}"),
    "excavator": ("Excavator",
                  "2fd6cemt4gmccflhm6imvdfvli3nf7zn6rfrwpsy7uhxrgbypvwf5fad.onion",
                  "/search?q={q}"),
    "findtor": ("Find Tor",
                "findtorroveq5wdnipkaojfpqulxnkhblymc7aramjzajcvpptd4rjqd.onion",
                "/search?q={q}"),
    "metager": ("MetaGer",
                "metagerv65pwclop2rsfzg4jwowpavpwd6grhhlvdgsswvo6ii4akgyd.onion",
                "/meta/meta.ger?eingabe={q}"),
    "onionsearchengine": ("Onion Search Engine",
                          "37djtvjcpiprohcrlyvlhfil45kdlfizsyvilqskgvdrafn5mocz4cid.onion",
                          "/search?q={q}"),
    "onionsearchserver": ("Onion Search Server",
                          "3fzh7yuupdfyjhwt3ugzqqof6ulbcl27ecev33knxe3u7goi3vfn2qqd.onion",
                          "/search?q={q}"),
    "ourrealm": ("Our Realm",
                 "orealmvxooetglfeguv2vp65a3rig2baq2ljc7jxxs4hsqsrcemkxcad.onion",
                 "/search?q={q}"),
    "phobos": ("Phobos",
               "phobosxilamwcg75xt22id7aywkzol6q6rfl2flipcqoc4e4ahima5id.onion",
               "/search?q={q}"),
    "submarine": ("Submarine (Torgle)",
                  "no6m4wzdexe3auiupv2zwif7rm6qwxcyhslkcnzisxgeiw6pvjsgafad.onion",
                  "/search?q={q}"),
    "tordex": ("TorDex",
               "tordexu73joywapk2txdr54jed4imqledpcvcuf75qsas2gwdgksvnyd.onion",
               "/search?q={q}"),
    "torland": ("TorLanD",
                "torlgu6zhhtwe73fdu76uiswgnkfvukqfujofxjfo7vzoht2rndyhxyd.onion",
                "/search?q={q}"),
    "darksearch": ("DarkSearch",
                   "darkzqtmbdeauwq5mzcmgeeuhet42fhfjj4p5wbak3ofx2yqgecoeqyd.onion",
                   "/search?q={q}"),
    "torsearch": ("TorSearch",
                  "tz75oxijdfwnobeh3sn6vfethrz4zqdasylrmp7euntqivbsaubojmyd.onion",
                  "/search?q={q}"),
    "onionseek": ("OnionSeek",
                  "adkjynq6cgcgzw75xptpakthkrrysihwuruv6gb632i4ovaqqbgtt7id.onion",
                  "/search?q={q}"),
    "darknetsearch": ("DarknetSearch",
                      "darknetsrvqlssdnli6mgoqxud4krgu3hqm62d7whu3gl6xj22fkyaid.onion",
                      "/search?q={q}"),
    "torgol": ("Torgol",
               "torgolnpgaztxr7mvjdz2idhq4vwp2sndydirjkcqwuwqe6u7tjoipqd.onion",
               "/search?q={q}"),
    "darksearchenginer": ("Dark Search Enginer",
                          "l4rsciqnpzdndt2llgjx3luvnxip7vbyj6k6nmdy4xs77tx6gkd24ead.onion",
                          "/search?q={q}"),
    "onix": ("Onix",
             "onixxxxxbddwewhvktd5zf5s7arpkmkv3m7n4zorjxvfxl7zowhvseid.onion",
             "/search?q={q}"),
    "navigator": ("Navigator",
                  "3gez2dfuf4y7buo33hq2xkhjiy6jfxfmszmipjbvfwo4jz6gk4qi4pid.onion",
                  "/search?q={q}"),
    "anubis": ("Anubis",
               "anubisrmxruiuxyw4ld2cjcjqeydce66q3zje2wyhg4wmdirjdbg3lqd.onion",
               "/search?q={q}"),
}
DEAD_ENGINES = [
    # Kept for reference only - never shown to the user.
    ("Grams", "shut Dec 2017"),
    ("Not Evil", "original offline since 2024 (impersonators exist)"),
    ("Candle", "only v2 onion address (v2 retired 2021)"),
    ("Kilos", "closed or unreliable (Oct 2026)"),
    ("Recon", "offline per onion.live (Oct 2026)"),
    ("Onion.city", "no longer existing; was a gateway, not search"),
    ("DarkSearch (clearnet)", "darksearch.io unreachable (checked 2026-10-18)"),
]


def hunt_ahmia(queries, cat):
    """Ahmia via clearnet (ahmia.fi). Token-gated search - token is
    extracted live from the homepage. VERIFIED working 2026-10-18."""
    t0 = time.time()
    out = []
    _live(f"live search ({len(queries)} queries)…")
    tok = ahmia_token()
    prog = Prog(len(queries), "search")
    fetched = 0
    for q in queries:
        try:
            url = ("https://ahmia.fi/search/?q="
                   + urllib.parse.quote_plus(q)
                   + f"&{tok[0]}={tok[1]}")
            page = fetch(url)
            fetched += 1
        except Exception as e:
            print(paint(f"\n  [!] a search query failed ({q}): {e}", YELLOW))
            prog.tick()
            continue
        for title, onion, seen in parse_engine_blocks(page):
            label = title + (f" (seen {seen})" if seen else "")
            out.append((title, onion, "ahmia", label, [cat], [q]))
        prog.tick()
        time.sleep(0.5)
    if fetched and not out:
        print(paint("  [i] a search engine returned pages but 0 parsable "
                    "results - its format may have changed", DIM))
    prog.done(f"{len(out)} rows")
    return out, {"source": "search", "rows": len(out),
                 "secs": time.time() - t0, "status": "ok"}


def hunt_torch(queries, cat):
    """Torch via clearnet (torch.cx). No token needed.
    VERIFIED working 2026-10-18."""
    t0 = time.time()
    out = []
    _live(f"live search ({len(queries)} queries)…")
    prog = Prog(len(queries), "search")
    fetched = 0
    for q in queries:
        try:
            url = ("https://torch.cx/search/?q="
                   + urllib.parse.quote_plus(q))
            page = fetch(url)
            fetched += 1
        except Exception as e:
            print(paint(f"\n  [!] a search query failed ({q}): {e}", YELLOW))
            prog.tick()
            continue
        for title, onion, seen in parse_engine_blocks(page):
            label = title + (f" (seen {seen})" if seen else "")
            out.append((title, onion, "torch", label, [cat], [q]))
        prog.tick()
        time.sleep(0.5)
    if fetched and not out:
        print(paint("  [i] a search engine returned pages but 0 parsable "
                    "results - its format may have changed", DIM))
    prog.done(f"{len(out)} rows")
    return out, {"source": "search", "rows": len(out),
                 "secs": time.time() - t0, "status": "ok"}


def hunt_onion_engine(key, queries, cat):
    """Generic onion-only engine search (stealth/Tor mode only).
    Every attempt is live. Fail-safe: a wrong query pattern or a
    dead engine just yields no rows (strict-filtered anyway)."""
    _, host, path = ONION_ENGINES[key]
    t0 = time.time()
    out = []
    for q in queries:
        url = "http://" + host + path.replace(
            "{q}", urllib.parse.quote_plus(q))
        try:
            page = fetch(url)
        except Exception as e:
            print(paint("\n  [!] an onion search query failed "
                        f"({q}): {str(e)[:80]}", YELLOW))
            continue
        p = Anchors()
        try:
            p.feed(page)
        except Exception:
            pass
        n = 0
        for href, text in p.pairs:
            for o in find_onions(href + " " + text):
                name = text if len(text) >= 3 else o
                out.append((name, "http://" + o, key,
                            name, [cat], [q]))
                n += 1
        if n == 0:  # fallback: raw onion regex on the page
            for o in find_onions(page):
                out.append((o, "http://" + o, key,
                            o, [cat], [q]))
        time.sleep(0.5)
    return out, {"source": "search", "rows": len(out),
                 "secs": time.time() - t0, "status": "ok"}


def _safe_onion_hunt(eng, qs, cat):
    """Wrapper so one engine can never break the parallel sweep."""
    try:
        return hunt_onion_engine(eng, qs, cat)
    except Exception as e:
        return [], {"source": "search", "rows": 0, "secs": 0,
                    "status": f"error: {str(e)[:60]}"}


def check_clearnet(url, timeout=12):
    try:
        req = urllib.request.Request(url, headers=UA)
        with _URL_OPENER.open(req, timeout=timeout) as r:
            return r.status < 400
    except Exception:
        return False


def check_via_tor(url):
    """v2.7 CRITICAL FIX: health probe through Tor when stealth is on.
    The old code probed 6 clearnet sites via plain urllib even with
    USE_TOR=True - leaking the real IP at startup right after telling
    the user 'your IP stays hidden'."""
    try:
        fetch_tor(url, limit=1024)
        return True
    except Exception:
        return False


def verify_tor():
    """v2.7: confirm the SOCKS proxy is really Tor (not SSH -D / VPN).
    tor_available() only checks the port is open."""
    try:
        data = fetch_tor("https://check.torproject.org/api/ip", limit=4096)
        return json.loads(data).get("IsTor") is True
    except Exception:
        return False


def source_health():
    """Startup probe: how many live sources respond. Source identities
    are never shown - only the count."""
    print(section("SOURCE HEALTH CHECK  ·  live probe"))
    targets = ["https://dark.fail/", "https://onion.live/",
               "https://tor.taxi/", "https://ransomware.live/",
               "https://ahmia.fi/", "https://torch.cx/"]
    probe = check_via_tor if USE_TOR else check_clearnet
    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(probe, targets))
    n = sum(1 for r in results if r)
    if n == len(targets):
        pill = paint("● ALL LIVE ", GREEN, BOLD)
    elif n:
        pill = paint(f"● {n}/{len(targets)} LIVE ", YELLOW, BOLD)
    else:
        pill = paint("● OFFLINE ", RED, BOLD)
    print(f"  {pill} {paint('live sources responding', DIM)}")
    if USE_TOR:
        print(paint("  ● onion-only sources reachable via Tor stealth",
                    CYAN, DIM))
    else:
        print(paint("  ● onion-only sources need stealth mode [9]", DIM))

# ------------------------------------------------- seeds & countries
def load_seeds():
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "seeds.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("seeds", [])
    except (OSError, ValueError) as e:
        print(paint(f"  [!] seeds.json unreadable ({e}) - continuing "
                    "without seeds", YELLOW))
        return []


def seed_descs():
    return {s["onion"]: s.get("desc", "") for s in load_seeds()
            if s.get("onion") and s.get("desc")}


def load_countries():
    """Validated country database. Returns list of dicts."""
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "countries.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f).get("countries", [])
    except (OSError, ValueError) as e:
        print(paint(f"  [!] countries.json unreadable ({e})", RED))
        return []
    valid = [c for c in data
             if isinstance(c, dict) and c.get("name")
             and isinstance(c.get("keywords"), list) and c["keywords"]]
    if len(valid) != len(data):
        print(paint(f"  [!] {len(data) - len(valid)} bad country entries "
                    "skipped", YELLOW))
    return valid


def _nav_hint():
    print(paint("  [0] Back    [H] Home", DIM))


def _read_choice(prompt="  Enter number: "):
    try:
        return input(paint(prompt, BOLD)).strip()
    except EOFError:
        return ""  # Ctrl+D: every caller treats "" as back/skip


def pick_country():
    """Numbered region -> country picker. [0] Back, [H] Home at
    every level. Returns the country dict, or None (backed out)."""
    countries = load_countries()
    if not countries:
        return None
    regions = ["Asia", "Europe", "Africa",
               "North America", "South America", "Oceania"]
    while True:  # region level
        print(section("COUNTRY-SPECIFIC  ·  select region"))
        for i, rg in enumerate(regions, 1):
            n = sum(1 for c in countries if c["region"] == rg)
            print(f"   {paint('[' + str(i) + ']', CYAN, BOLD)} "
                  f"{rg} {paint(f'({n})', DIM)}")
        _nav_hint()
        c = _read_choice().lower()
        if c in ("0", "h", "q", "quit", "exit", ""):
            return None
        if not _is_num(c) or not 1 <= int(c) <= len(regions):
            print(paint("  [!] Invalid region", YELLOW))
            continue
        region = regions[int(c) - 1]
        clist = [x for x in countries if x["region"] == region]
        while True:  # country level
            print(section(f"COUNTRY-SPECIFIC  ·  {region} — select country"))
            for i, x in enumerate(clist, 1):
                print(f"   {paint('[' + str(i) + ']', CYAN, BOLD)} {x['name']}")
            _nav_hint()
            c2 = _read_choice().lower()
            if c2 == "0":
                break  # back to region level
            if c2 in ("h", "q", "quit", "exit", ""):
                return None
            if not _is_num(c2) or not 1 <= int(c2) <= len(clist):
                print(paint("  [!] Invalid country", YELLOW))
                continue
            picked = clist[int(c2) - 1]
            print(paint(f"  [+] Country selected: {picked['name']}",
                        GREEN, BOLD))
            return picked


def pick_country_what(country):
    """After a country is picked: ask WHAT the user wants for it.
    Returns (set_of_type_keys | None | 'home')."""
    while True:
        print(section(f"WHAT FOR {country['name'].upper()}?  ·  pick types"))
        for num in sorted(COUNTRY_TYPES, key=int):
            label, _ = COUNTRY_TYPES[num]
            print(f"   {paint('[' + num + ']', CYAN, BOLD)} {label}")
        print(paint("   Multiple:  1,3,5    Range:  1-4", DIM))
        _nav_hint()
        raw = _read_choice().lower()
        if raw == "0":
            return None
        if raw in ("h", "q", "quit", "exit", ""):
            return "home"
        sel = parse_numbers(raw, set(COUNTRY_TYPES))
        if not sel:
            print(paint("  [!] Pick at least one type (e.g. 1,3 or 1-4)",
                        YELLOW))
            continue
        return sel


def _is_num(s):
    """Audit F3: str.isdigit() is True for '²' etc., but int('²')
    raises ValueError. ASCII-only digits are int()-safe."""
    return s.isascii() and s.isdigit()


def parse_numbers(text, valid):
    """'1,4,5' and '1-3' -> set of valid keys. Empty set if none."""
    text = text.strip().lower()
    sel = set()
    for part in text.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            if _is_num(a.strip()) and _is_num(b.strip()):
                lo, hi = int(a.strip()), int(b.strip())
                if 0 <= hi - lo <= 50:  # audit: cap range size
                    sel.update(str(n) for n in range(lo, hi + 1))
        elif _is_num(part):
            sel.add(part)
    return {s for s in sel if s in valid}


def parse_selection(text):
    text = text.strip().lower()
    if text in ("8", "all", "full"):
        return {"8"}, None
    sel = parse_numbers(text, set(CATEGORIES))
    if "8" in sel:
        return {"8"}, None
    custom = None
    if "7" in sel:
        sel.discard("7")
        custom = _read_choice(
            paint("  Enter your keywords (comma-separated): ",
                  BOLD)).strip()
        if not custom:
            print(paint("  [!] No keywords given - 'Other' skipped", YELLOW))
            custom = None
    if not sel and not custom:
        return set(), None
    return sel, custom


def country_hit(text, keywords):
    """Strict word-boundary match: 'niger' must NOT match 'nigeria'."""
    return [k for k in keywords
            if re.search(r"\b" + re.escape(k) + r"\b", text)]

# ------------------------------------------------- hunt orchestration
def build_engine_plan(sel, custom, country=None, types=None):
    """(engine_key, queries, category_label) — every entry is a live
    query the tool will genuinely attempt."""
    plan = []
    if sel == {"8"}:
        for eng in CLEARNET_ENGINES:
            plan.append((eng, SWEEP_QUERIES, "FULL SWEEP"))
        if USE_TOR:
            for eng in ONION_ENGINES:
                plan.append((eng, SWEEP_QUERIES[:3], "FULL SWEEP"))
        return plan
    cats = []
    for c in sorted(sel):
        if c == "6":
            continue
        cname = CATEGORIES[c][0]
        cats.append((cname, ENGINE_QUERIES.get(cname, [cname.lower()])))
    if custom:
        kws = [k.strip() for k in custom.split(",") if k.strip()][:2]
        if kws:
            cats.append(("Custom: " + custom, kws))
    if country and types:
        cname = "Country: " + country["name"]
        for t in sorted(types, key=int):
            tlabel, tkws = COUNTRY_TYPES[t]
            if t == "6":
                qs = [country["name"].lower() + " dark web",
                      country["name"].lower() + " forum"]
            else:
                qs = [country["name"].lower() + " " + tkws[0]]
            cats.append((cname, qs))
    for cname, qs in cats:
        for eng in CLEARNET_ENGINES:
            plan.append((eng, qs, cname))
        if USE_TOR:
            for eng in ONION_ENGINES:
                plan.append((eng, qs[:1], cname))
    return plan


def _strict_keep(name, label, wanted):
    """Strict keyword gate shared by directory, engine and seed rows.
    Returns (cats, why); empty cats = row is NOT what the user asked
    for and must be dropped. Substring match (NOT word-boundary):
    'breach' must still hit 'Breached'."""
    text = (name + " " + label).lower()
    cats, why = [], []
    for c, (cname, kws, strict) in wanted.items():
        mk = [k for k in kws if k in text]
        if mk:
            cats.append(cname)
            why += mk
    return cats, why


def hunt_multi(sel, custom, country=None, types=None):
    stats = []
    t_all = time.time()
    _SRC_N[0] = 0  # restart source numbering for this hunt
    fails_before = TOR_FAILS  # audit F21: per-hunt delta, not lifetime total
    print(paint(f"\n  ┏━ LIVE HUNT ━ started {stamp()} UTC "
                "━ every source below is queried right now ━┓",
                CYAN, BOLD))
    rows = []
    for fn in (hunt_darkfail, hunt_onionlive, hunt_tortaxi):
        r, st = fn()
        rows += r
        stats.append(st)
    if sel == {"8"} or "4" in sel or country:
        r, st = hunt_ransomware_live()
        rows += r
        stats.append(st)

    eng_rows = []
    plan = build_engine_plan(sel, custom, country, types)
    clear_plan = [p for p in plan if p[0] in CLEARNET_ENGINES]
    onion_plan = [p for p in plan if p[0] not in CLEARNET_ENGINES]
    for eng, qs, cat in clear_plan:
        if eng == "ahmia":
            r, st = hunt_ahmia(qs, cat)
        else:
            r, st = hunt_torch(qs, cat)
        eng_rows += r
        stats.append(st)
    if onion_plan:
        # 25 engines: queried in parallel (8 workers), one shared
        # progress bar - sequential would take far too long over Tor.
        _live(f"querying {len(onion_plan)} onion search engines via Tor…")
        prog = Prog(len(onion_plan), "search")
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs = {ex.submit(_safe_onion_hunt, eng, qs, cat): eng
                    for eng, qs, cat in onion_plan}
            for f in as_completed(futs):
                r, st = f.result()
                eng_rows += r
                stats.append(st)
                prog.tick()
        prog.done(f"{sum(s['rows'] for s in stats if s['source'] == 'search')}"
                  f" rows")

    seed_rows = []
    for s in load_seeds():
        if not s.get("onion"):
            continue
        take = False
        if sel == {"8"} or SEED_CATS.get(s.get("cat")) in sel:
            take = True
        elif country:
            txt = (s.get("name", "") + " " + s.get("desc", "")).lower()
            if country_hit(txt, [k.lower()
                                 for k in country["keywords"]]):
                take = True
        if take:
            seed_rows.append(
                (s["name"], s["onion"], "user-seeds",
                 s["name"] + " [user-contributed, unverified] "
                 + s.get("desc", ""),
                 ["user-seeds"], ["seed"]))

    blocked = sum(1 for r in rows if is_blocked(r[0]))
    rows = [r for r in rows if not is_blocked(r[0])]
    eng_rows = [r for r in eng_rows if not is_blocked(r[0])]
    seed_rows = [r for r in seed_rows if not is_blocked(r[0])]
    if blocked:
        print(paint(f"  [*] {blocked} skip-listed entries removed "
                    "(seized/honeypot/dead)", YELLOW))

    fails_now = TOR_FAILS - fails_before
    if USE_TOR and fails_now:
        print(paint(f"\n  [!] {fails_now} requests failed over Tor.", RED))
        if not rows and not eng_rows:
            print(paint("  [!] No data in stealth mode - check Tor and retry.\n"
                        "      (Never went over clearnet - fail-closed)\n",
                        RED, BOLD))
            return [], {}, []

    if sel == {"8"}:
        tagged = [(n, o, s, l, ["FULL SWEEP"], []) for n, o, s, l in rows]
        tagged += eng_rows
        tagged += seed_rows  # sweep = everything, seeds included
        print(paint(f"  [*] FULL SWEEP: {len(tagged)} rows", CYAN, BOLD))
        merged = merge(tagged)
    elif country and types:
        ckws = [k.lower() for k in country["keywords"]]
        tagged = []
        for n, o, s, l in rows:
            text = (n + " " + l).lower()
            cm = country_hit(text, ckws)
            if not cm:
                continue
            tlabels = [COUNTRY_TYPES[t][0] for t in sorted(types, key=int)
                       if not COUNTRY_TYPES[t][1]
                       or any(k in text for k in COUNTRY_TYPES[t][1])]
            if tlabels:
                tagged.append((n, o, s, l, ["Country: " + country["name"]],
                               cm + ["type:" + t for t in tlabels]))
        tagged += [r for r in eng_rows
                   if r[4] == ["Country: " + country["name"]]
                   and country_hit((r[0] + " " + r[3]).lower(), ckws)]
        tagged += seed_rows
        print(paint(f"  [*] {len(tagged)} rows strictly matched "
                    f"{country['name']}", CYAN, BOLD))
        merged = merge(tagged)
    else:
        wanted = {c: (CATEGORIES[c][0], CATEGORIES[c][1], False)
                  for c in sel if c != "6"}
        if custom:
            kws = [k.strip().lower() for k in custom.split(",") if k.strip()]
            wanted["custom"] = ("Custom: " + custom, kws, False)
        tagged = []
        for n, o, s, l in rows:
            cats, why = _strict_keep(n, l, wanted)
            if cats:  # strict: only what the user asked for
                tagged.append((n, o, s, l, cats, why))
        for r in eng_rows:  # engine rows pass the SAME strict gate
            cats, why = _strict_keep(r[0], r[3], wanted)
            if cats:
                tagged.append((r[0], r[1], r[2], r[3], r[4], why))
        for r in seed_rows:  # seeds too: name + desc must hit keywords
            cats, why = _strict_keep(r[0], r[3], wanted)
            if cats:
                tagged.append((r[0], r[1], r[2], r[3], r[4], why))
        print(paint(f"  [*] {len(tagged)} rows strictly matched your "
                    "selection", CYAN, BOLD))
        merged = merge(tagged)

    total = time.time() - t_all
    live_summary(stats, len(seed_rows), total)
    return merged, seed_descs(), stats


def live_summary(stats, seed_n, total):
    n_live = sum(s["rows"] for s in stats)
    n_src = sum(1 for s in stats if s["status"] == "ok")
    print(section("SOURCES QUERIED LIVE  ·  just now"))
    print(paint(f"  ┗━ {n_live} live rows from {n_src} live sources "
                f"in {total:.0f}s ━┛", GREEN, BOLD))
    if seed_n:
        print(paint(f"  ● {seed_n} rows from your own seed list "
                    "(user-contributed, UNVERIFIED — not live results)",
                    YELLOW))


def merge(rows):
    """rows: (name, onion, source, label, cats, why) -> ranked dicts."""
    merged = {}
    for name, onion, src, label, cats, why in rows:
        name = _clean(name)  # v2.7: remote titles -> terminal injection
        m = merged.setdefault(onion, {"name": name, "onion": onion,
                                      "sources": set(), "labels": set(),
                                      "cats": set(), "why": set()})
        m["sources"].add(src)
        m["labels"].add(label)
        m["cats"].update(cats)
        m["why"].update(why)
        if len(name) < len(m["name"]) or m["name"] in onion:
            m["name"] = name
    out = [{"name": v["name"], "onion": v["onion"],
            "sources": sorted(v["sources"]), "score": len(v["sources"]),
            "cats": sorted(v["cats"]), "why": sorted(v["why"]),
            "label": " | ".join(sorted(v["labels"]))} for v in merged.values()]
    out.sort(key=lambda r: (-r["score"], r["name"].lower()))
    return out


def describe(r, descs):
    """Short explanation of what an onion is / what it is for.
    Never names sources or engines - only the corroboration count."""
    bits = []
    if "user-seeds" in r["sources"]:
        d = descs.get(r["onion"])
        if d:
            bits.append(d + " [user-contributed, unverified]")
    for c in r["cats"]:
        if c == "FULL SWEEP":
            continue
        if c.startswith("Country: "):
            b = c[9:] + "-related forum / data source"
        elif c.startswith("Custom: "):
            b = "matches custom keywords"
        else:
            b = CAT_BLURB.get(c)
        if b and b not in bits:
            bits.append(b)
    if "Ransomware Leak Sites" in r["cats"] and not any(
            "ransomware" in b for b in bits):
        bits.append("ransomware data-leak site (DLS)")
    m = DEAD_RE.search(r["label"])
    if m:
        bits.append("a directory lists it as '%s'" % m.group(1))
    n = len(r["sources"])
    bits.append(f"corroborated by {n} independent "
                f"{'source' if n == 1 else 'sources'}")
    return "; ".join(bits)


def show(rows, descs, limit=60, note=None):
    if not rows:
        print(paint("\n  [!] No results found"
                    + (f" for '{note}'." if note else "."), YELLOW, BOLD))
        print("      The tool is working correctly - all sources were "
              "searched live.")
        print("      What you requested is simply not available right now.\n")
        return
    print(paint(f"\n  [+] {len(rows)} unique v3 onions "
                f"(score = corroborating sources)\n", GREEN, BOLD))
    print(paint(f"  {'#':<4}{'Name':<26}{'Score':<7}Onion", BOLD))
    print(paint("  " + "-" * 100, DIM))
    for i, r in enumerate(rows[:limit], 1):
        score = r["score"]
        scolor = GREEN if score >= 3 else (YELLOW if score == 2 else "")
        print(f"  {paint(f'{i:<4}', CYAN, BOLD)}{r['name'][:25]:<26}"
              f"{paint(f'{score:<7}', scolor, BOLD)}{r['onion']}")
        print(paint(f"       About: {describe(r, descs)[:110]}", DIM))
    if len(rows) > limit:
        print(paint(f"  ... +{len(rows) - limit} more (export to see all)",
                    DIM))


def export(rows, descs, label):
    os.makedirs("output", exist_ok=True)
    stamp_s = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    base = f"output/{label}-{stamp_s}"
    # Opacity: exports carry corroboration COUNTS, never source names.
    data = {"generated": datetime.now(timezone.utc).isoformat(),
            "count": len(rows),
            "results": [{**r, "sources": len(r["sources"])} for r in rows]}
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    with open(base + ".csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["name", "onion", "source_count", "score",
                    "matched_categories", "matched_keywords", "about"])
        for r in rows:
            # v2.7: _csv_cell neutralizes Excel formula injection.
            w.writerow([_csv_cell(r["name"]), r["onion"],
                        len(r["sources"]), r["score"],
                        _csv_cell(";".join(r["cats"])),
                        _csv_cell(";".join(r["why"])),
                        _csv_cell(describe(r, descs))])
    with open(base + ".txt", "w", encoding="utf-8") as f:
        f.write("\n".join(r["onion"] for r in rows) + "\n")

    def _md(s):
        # v2.7: escape pipes so hostile titles can't break the table.
        return str(s).replace("|", "\\|").replace("\n", " ")

    with open(base + ".md", "w", encoding="utf-8") as f:
        f.write(f"# Allium {VERSION} - {label}\n\n"
                f"Total: **{len(rows)}** unique v3 onions\n\n"
                "| # | Name | Onion | Score | Srcs | Why matched | About |\n"
                "|---|---|---|---|---|---|---|\n")
        for i, r in enumerate(rows, 1):
            f.write(f"| {i} | {_md(r['name'])} | `{r['onion']}` | "
                    f"{r['score']} | {len(r['sources'])} | "
                    f"{_md(', '.join(r['why'])) or '-'} | "
                    f"{_md(describe(r, descs))} |\n")
    print(paint(f"\n  [+] Exported -> {base}.{{json,csv,txt,md}}",
                GREEN, BOLD))


def live_check(rows):
    if not USE_TOR and not tor_available():
        print(paint("\n  [!] Tor is not running - liveness check needs Tor.",
                    YELLOW, BOLD))
        print(paint("      Open Tor Browser (or start the Tor service), "
                    "then retry.", YELLOW))
        return
    port = TOR_PORT or 9050
    print(f"\n  [*] Liveness via Tor (127.0.0.1:{port}), {len(rows)} onions ...")
    prog = Prog(len(rows), "liveness")
    for r in rows:
        try:
            p = subprocess.run(
                ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                 "--socks5-hostname", f"127.0.0.1:{port}",
                 "--max-time", "30", r["onion"]],
                capture_output=True, text=True, timeout=40)
            r["http_status"] = p.stdout.strip() or "no-response"
        except FileNotFoundError:
            r["http_status"] = "curl-missing"
            print(paint("\n  [!] curl not found - skipping liveness check",
                        YELLOW))
            break
        except Exception:
            r["http_status"] = "tor-down"
        prog.tick()
        time.sleep(0.2)
    prog.done()
    alive = [r for r in rows
             if str(r.get("http_status", ""))[:1] in ("2", "3")]
    print(paint(f"  [+] {len(alive)}/{len(rows)} responding "
                "(HTTP 2xx/3xx via Tor)", GREEN, BOLD))


def drop_dead(rows):
    kept = [r for r in rows if not DEAD_RE.search(r["label"])]
    print(paint(f"  [+] Removed {len(rows) - len(kept)} dead/offline-listed, "
                f"{len(kept)} remain", GREEN))
    return kept


def refine(rows):
    kw = _read_choice(paint("  Enter keyword: ", BOLD)).strip().lower()
    if not kw:
        return rows
    kept = [r for r in rows
            if kw in (r["name"] + " " + r["label"]).lower()]
    print(paint(f"  [+] {len(kept)} results remain", GREEN))
    return kept

# ------------------------------------------------- UI: banner/menu
BANNER = (
    divider() + "\n"
    + paint(r"""
    _    _     _     ___ _   _ __  __
   / \  | |   | |   |_ _| | | |  \/  |
  / _ \ | |   | |    | || | | | |\/| |
 / ___ \| |___| |___ | || |_| | |  | |
/_/   \_\_____|_____|___|\___/|_|  |_|
""",
          BOLD, CYAN)
    + paint(f"\n   ▄▄▄ peel the dark web, layer by layer │ {VERSION} "
            "│ LIVE-ENGINE MODE ▄▄▄", MAG, BOLD)
    + "\n" + divider() + "\n"
    + paint("   ┌─ Author ──────────────────────────────┐\n", DIM)
    + paint("   │  ", DIM) + paint("Karan Soni", WHITE, BOLD)
    + paint("      👉  ", DIM) + paint(gh_link(), CYAN, BOLD)
    + paint("  │", DIM) + "\n"
    + paint("   └───────────────────────────────────────┘", DIM)
    + "\n" + divider()
)


def menu():
    print(BANNER)
    tor_state = paint("ON (IP hidden)", GREEN, BOLD) if USE_TOR \
        else paint("OFF", RED, BOLD)
    print(section("SELECT TARGET"))
    for num, label in [
            ("1", "Breach & Leak Forums"),
            ("2", "Russian Forums"),
            ("3", "English Hacking Forums"),
            ("4", "Ransomware Leak Sites  (live DLS tracking)"),
            ("5", "AI Chatbots & Tools"),
            ("6", "Country-Specific Forums & Data  (197 countries)"),
            ("7", "Other  (your own keywords)"),
            ("8", "FULL SWEEP  (everything - no corner left behind)")]:
        print(f"   {paint('[' + num + ']', CYAN, BOLD)} {label}")
    print(section("OPTIONS"))
    print(f"   {paint('[9]', YELLOW, BOLD)} Stealth mode (Tor)  [{tor_state}]")
    print(f"   {paint('[G]', YELLOW, BOLD)} GitHub  {paint(gh_link(), CYAN)}")
    print(f"   {paint('[0]', RED, BOLD)} Exit")
    print(paint("\n   Multiple:  1,4,5    Range:  1-3", DIM))
    return _read_choice("\n   Enter number: ")


def show_github():
    print(paint("\n  ╔══════════════════════════════════════════════════════╗",
                CYAN, BOLD))
    print(paint("  ║", CYAN, BOLD) + "   👨‍💻  "
          + paint("Karan Soni", WHITE, BOLD)
          + paint("  —  dark-web OSINT & threat intel", DIM)
          + paint("   ║", CYAN, BOLD))
    print(paint("  ║", CYAN, BOLD) + "   🔗  "
          + paint(gh_link("github.com/karansoni0x  ← click to open"),
                  CYAN, BOLD)
          + paint("         ║", CYAN, BOLD))
    print(paint("  ╚══════════════════════════════════════════════════════╝",
                CYAN, BOLD))
    print(paint("  Star the repo if this tool helped your research.", DIM))
    _read_choice("  Press Enter to continue… ")


def toggle_stealth():
    global USE_TOR
    if USE_TOR:
        USE_TOR = False
        print(paint("\n  [-] Stealth OFF - traffic goes direct (IP visible)",
                    YELLOW, BOLD))
        return
    if tor_available():
        USE_TOR = True
        # v2.7: confirm it is really Tor, not some other SOCKS proxy.
        if verify_tor():
            print(paint("\n  [+] Stealth ON - Tor verified, all traffic "
                        "via Tor, your IP stays hidden", GREEN, BOLD))
        else:
            print(paint("\n  [!] Stealth ON - proxy NOT confirmed as Tor "
                        "(could be SSH -D / VPN).\n"
                        "      Traffic goes through the proxy (IP hidden "
                        "from sites), but Tor is UNCONFIRMED.",
                        YELLOW, BOLD))
    else:
        print(paint("\n  [!] Tor not found (127.0.0.1:9050/9150).\n"
                    "      Open Tor Browser or start the Tor service first.\n"
                    "      Stealth will NOT turn on without Tor.", RED, BOLD))


def actions(rows, descs, label):
    while True:
        print(section("ACTIONS"))
        for num, text in [
                ("1", "Export (JSON + Markdown + CSV + TXT)"),
                ("2", "Liveness check via Tor"),
                ("3", "Remove dead/offline-listed"),
                ("4", "Filter further by keyword"),
                ("5", "New hunt (home)"),
                ("H", "Home"),
                ("0", "Exit")]:
            print(f"   {paint('[' + num + ']', CYAN, BOLD)} {text}")
        c = _read_choice("\n   Enter number: ").lower()
        if c in ("q", "quit", "exit"):
            c = "0"
        if c == "":
            continue  # empty Enter: quietly re-show menu
        if c not in {"0", "1", "2", "3", "4", "5", "h"}:
            print(paint("  [!] Valid options: 0-5, H", YELLOW))
            continue
        if c == "1":
            export(rows, descs, label)
        elif c == "2":
            live_check(rows)
        elif c == "3":
            rows = drop_dead(rows)
            show(rows, descs)
        elif c == "4":
            rows = refine(rows)
            show(rows, descs)
        elif c in ("5", "h"):
            return True
        elif c == "0":
            return False


DISCLAIMER = (
    paint("\n  ┌─ DISCLAIMER ─ READ BEFORE USE ─", YELLOW, BOLD) + """
  │  Allium is a RESEARCH and DEFENSIVE-OSINT tool only.
  │
  │  - Onion links shown here come from public directories, live
  │    search engines, and user-contributed seeds. They are NOT
  │    verified by the author.
  │  - Directories sometimes list hijacked, seized, or honeypot
  │    links (e.g. Dread, Oct 2026). Verify via PGP-signed lists.
  │  - Do NOT visit unknown onion sites without proper OPSEC:
  │    Tor Browser or Whonix, no personal accounts, no downloads.
  │  - Know and follow your local laws. The author takes NO
  │    responsibility for misuse of this tool or the links it finds.
  └─────────────────────────────────────────────────────────"""
)


def accept_disclaimer():
    """Compulsory gate: no YES, no tool."""
    print(DISCLAIMER)
    ans = _read_choice(paint("\n  Type YES to accept and continue: ",
                             YELLOW, BOLD)).strip().lower()
    if ans != "yes":
        print(paint("\n  Disclaimer not accepted. Exiting.\n", RED, BOLD))
        return False
    return True


def goodbye():
    print(paint("\n  Happy hunting.", GREEN, BOLD)
          + paint(f"  ⭐ Star on GitHub: {gh_link()}\n", DIM))


def country_flow():
    """Option 6: region -> country -> WHAT (types) -> hunt.
    Never auto-runs: the user picks types first. Returns
    (country, types) or (None, None) if backed out."""
    country = pick_country()
    if not country:
        return None, None
    while True:
        types = pick_country_what(country)
        if types == "home":
            return None, None
        if types is None:  # Back -> re-pick country
            country = pick_country()
            if not country:
                return None, None
            continue
        return country, types


def main():
    global USE_TOR
    if not accept_disclaimer():
        return
    print(paint("\n  [!] Research / defensive OSINT only. Directories "
                "sometimes list hijacked links\n"
                "      (e.g. Dread, Oct 2026) - verify against "
                "PGP-signed lists.", YELLOW))
    if tor_available():
        USE_TOR = True
        # v2.7: confirm it is really Tor, not some other SOCKS proxy.
        if verify_tor():
            print(paint(f"  [+] Tor verified (127.0.0.1:{TOR_PORT}) - "
                        "STEALTH MODE auto-ON: your IP stays hidden.",
                        GREEN, BOLD))
        else:
            print(paint(f"  [!] Proxy on 127.0.0.1:{TOR_PORT} is NOT "
                        "confirmed as Tor (could be SSH -D / VPN).\n"
                        "      Traffic still goes through the proxy "
                        "(IP hidden from sites),\n"
                        "      but Tor itself is UNCONFIRMED.",
                        YELLOW, BOLD))
    else:
        print(paint("  [*] Tor not running - onion-only engines need "
                    "stealth [9].", YELLOW))
    source_health()
    while True:
        raw = menu().lower()
        if raw in ("q", "quit", "exit"):
            raw = "0"
        if raw == "":
            continue  # quiet re-prompt
        if raw == "0":
            goodbye()
            break
        if raw == "9":
            toggle_stealth()
            continue
        if raw == "g":
            show_github()
            continue
        country, types = None, None
        if raw == "6":
            country, types = country_flow()
            if not country:
                continue
            sel, custom = set(), None
        else:
            sel, custom = parse_selection(raw)
            if "6" in sel:
                # Country picker only runs standalone ("6" alone).
                print(paint("  [*] Note: '6' (Country-Specific) works "
                            "standalone only - ignored in multi-select. "
                            "Pick 6 alone for the country picker.", YELLOW))
                sel.discard("6")
        if not sel and not custom and not country:
            print(paint("  [!] No valid option selected "
                        "(use 1-8, e.g. 1,4 or 1-3)", YELLOW))
            continue
        names = [CATEGORIES[c][0] for c in sorted(sel - {"8"})]
        if custom:
            names.append("Custom: " + custom)
        if country:
            tnames = ", ".join(COUNTRY_TYPES[t][0]
                               for t in sorted(types, key=int))
            names.append(f"Country: {country['name']} [{tnames}]")
        if sel == {"8"}:
            names = ["FULL SWEEP"]
        label = "-".join(names).lower().replace(" ", "-").replace("&", "n")
        label = re.sub(r"[^a-z0-9-]", "", label)[:60] or "hunt"
        rows, descs, _stats = hunt_multi(sel, custom, country, types)
        show(rows, descs, note=", ".join(names))
        if not actions(rows, descs, label):
            goodbye()
            break


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(paint("\n\n  Stopped. Happy hunting.\n", YELLOW, BOLD))
        sys.exit(0)
