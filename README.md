# 🧅 Allium v2.6 PRO

**Dark web onion discovery engine** — menu-driven, zero dependencies, zero typing.
Built by [Karan Soni](https://github.com/karansoni0x).

Pick numbers. Get exactly what you asked for — strict filtering, every
result explained. Stealth mode keeps your IP invisible. **Every source is
queried live** — directories, search engines, ransomware DLS.

```
  [1] Breach & Leak Forums
  [2] Russian Forums
  [3] English Hacking Forums
  [4] Ransomware Leak Sites  (live DLS tracking)
  [5] AI Chatbots & Tools
  [6] Country-Specific Forums & Data  (197 countries)
  [7] Other  (your own keywords)
  [8] FULL SWEEP  (everything - no corner left behind)

  [9] Stealth mode (Tor)  [ON (IP hidden)]
  [G] GitHub  https://github.com/karansoni0x
  [0] Exit

  Multiple:  1,4,5    Range:  1-3
```

Option 6 opens a guided picker: **region → country → what do you want?**
The "what" step asks which onion types (forums, markets, leak sites,
ransomware DLS, AI tools, or all) — the hunt only runs after you choose.
Filtering is **word-boundary strict** - "Niger" never matches "Nigeria".

Every menu has **[0] Back** and **[H] Home** — no dead ends, never
re-run the script to change a selection.

## Why it's different

| Feature | Allium | Typical directory scrapers |
|---|---|---|
| Sources | 4 live directories + 27 live search engines | 1-3 static directories |
| Search engines | Ahmia + Torch (clearnet) + 25 verified onion engines via Tor | None - directories only |
| Ransomware leak sites | Live extraction from ransomware.live group profiles | None - static lists rot in weeks |
| Menu-driven | Numbered options, multi-select, ranges, custom keywords | CLI flags you must memorize |
| Strict filtering | Only what you selected - nothing else slips in | Fuzzy dumps |
| Result explanations | Every onion ships with a short "what is this" note | Bare URLs |
| Corroboration ranking | Links scored by # of independent sources | Flat dumps |
| Live proof | Per-source progress + "sources queried live" summary | Silent hangs |
| Dependencies | **Zero** - Python 3 stdlib only | Often need requests/bs4 |
| Liveness check | Optional, via local Tor SOCKS | Rarely included |
| Stealth mode | All traffic via Tor SOCKS5h, fail-closed | Clearnet only |

### Source health check

Every startup probes the live sources and prints a single status line —
how many sources respond right now. Source identities are never shown:
no engine names, no directory names, anywhere in the tool's output.
Results carry a corroboration **score** (number of independent sources),
never the source names.

### The ransomware.live trick

Ransomware leak-site onions rot faster than anything else. Allium
enumerates every `/group/<name>` page on ransomware.live and reads only
the **first 150KB** of each - the group profile (with leak-site onions)
sits at the top; the megabytes of victim posts below are skipped.
400+ groups scanned in under a minute, from the clearnet, no Tor needed
for discovery.

## Install

```bash
git clone https://github.com/karansoni0x/allium.git
cd allium
python3 allium.py
```

No `pip install`. No virtualenv. Python 3.8+ is all you need. Works on
Windows, Linux and macOS.

## Usage

```
$ python3 allium.py

  [1] Breach & Leak Forums
  [2] Russian Forums
  [3] English Hacking Forums
  [4] Ransomware Leak Sites  (live DLS tracking)
  [5] AI Chatbots & Tools
  [6] Country-Specific Forums & Data  (197 countries)
  [7] Other  (your own keywords)
  [8] FULL SWEEP  (everything - no corner left behind)
  [9] Stealth mode (Tor)  [ON (IP hidden)]
  [G] GitHub
  [0] Exit

  Multiple:  1,4,5    Range:  1-3

  Enter number: 1,4
```

**Note:** `6` (Country-Specific) only works **standalone** — it opens
the guided region → country picker. In a multi-select like `1,6`, the
`6` is ignored with a notice; pick `6` alone for the country flow.

Country flow: `6` → pick region → pick country → **pick what you want**
(forums / markets / leak sites / ransomware DLS / AI tools / all) →
hunt runs. Back out at any step with `[0]`, jump home with `[H]`.

Results are ranked by **score** = number of independent sources that
corroborate the onion. Higher score = more trustworthy. Every row shows
an **About** line explaining what the onion is and what it is for.

After a hunt you get a **"sources queried live"** summary — total live
rows, how many sources responded, and total time — so it's always clear
the results are fresh, not from a saved list. (Source identities are
never shown — that's the runtime opacity above.)

After a hunt:

```
  [1] Export (JSON + Markdown + CSV + TXT)
  [2] Liveness check via Tor   (needs Tor on 127.0.0.1:9050/9150)
  [3] Remove dead/offline-listed
  [4] Filter further by keyword
  [5] New hunt (home)
  [H] Home
  [0] Exit
```

## Sources

### Directories (queried live every hunt)

| Source | What it gives |
|---|---|
| [dark.fail](https://dark.fail) | PGP-signed service directory (most trustworthy) |
| [onion.live](https://onion.live) | 11 categories: forum, market, vendor, tools, ... |
| [tor.taxi](https://tor.taxi) | Clearnet onion index |
| [ransomware.live](https://ransomware.live) | Live ransomware group leak-site onions |
| `seeds.json` | User-contributed seed links — **labeled unverified, never presented as fresh results** |

### Search engines (queried live per hunt)

| Engine | Access | Status (checked 2026-10-18) | Notes |
|---|---|---|---|
| Ahmia | Clearnet ([ahmia.fi](https://ahmia.fi)) | ✅ LIVE | Filtered index; search token extracted live |
| Torch | Clearnet ([torch.cx](https://torch.cx)) | ✅ LIVE | Unfiltered index; no token needed |

Plus **25 verified onion-only search engines**, queried in parallel via
Tor stealth mode (8 concurrent workers, one shared progress bar):
Haystak, Tor66, OnionLand, Amnesia, Bobby, Deep Search, Excavator,
Find Tor, MetaGer, Onion Search Engine, Onion Search Server, Our Realm,
Phobos, Submarine (Torgle), TorDex, TorLanD, DarkSearch, TorSearch,
OnionSeek, DarknetSearch, Torgol, Dark Search Enginer, Onix, Navigator,
Anubis. All v3 addresses verified Oct 2026 against Avira's 2026 engine
guide, onion.live real-time checks, and the megadose/OnionSearch
project. Query patterns are best-effort — a wrong pattern just yields
no rows, and every row still passes the strict keyword filter.

Engines confirmed dead and **excluded** (never queried): Grams (shut
2017), Not Evil (original offline since 2024), Candle (v2-only), Kilos,
Recon, Onion.city, DarkSearch clearnet. ~20 more names from old
academic lists (GDark, GoDeep, Hologram, Hoodle, Kraken, Ondex, Search
Demon, Sentor, Stealth, TorBook, TOR Google, Tornet Global Search,
TorTorGo, Venus Search Engine, …) have no verifiable current address —
excluded rather than queried with guessed URLs.

> DuckDuckGo's onion is excluded deliberately — general web search,
> not onion discovery.

## Precision features (strict - only what you asked for)

- **Multi-select + ranges** - `1,4,5` or `1-3`: sources are hunted once,
  then a strict filter keeps only your selection.
- **Custom keywords** - option 7: type your own words, the tool hunts on them.
- **Country flow** - option 6 -> region -> country -> **what-types** ->
  only matching types shown. Nothing auto-runs before you choose.
- **Corroboration score** - every link scored by independent sources.
- **Match transparency** - every result shows *why* it matched
  (which keyword, which category). Full detail in exports.
- **Skip-list blocklist** - seized / honeypot-risk / dead entries
  (BreachForums, RAMP, Nulled, XSS.is, RansomHub, Hunters, Lynx, Medusa)
  auto-filtered.
- **Dead-listed filter** - entries directories mark `offline`/`dead`
  removed in one option.
- **Refine** - narrow results with another keyword, no re-hunt needed.
- **Back/Home everywhere** - `[0]` goes back one level, `[H]` jumps to
  the main menu. No dead-end screens.

## Stealth mode (no IP leak, no footprint)

```
  [9] Stealth mode (Tor)  [ON (IP hidden)]
```

- **Auto-ON when Tor is detected** at startup
  (9050 = system Tor, 9150 = Tor Browser).
- In stealth, **every request goes through Tor SOCKS5**: sites see the
  Tor exit IP, never yours. All 25 onion-only search engines become
  queryable (in parallel).
- **DNS resolved by Tor** (no DNS leak), no cookies, no identifying headers.
- **Fail-closed:** if Tor is missing or drops, the tool refuses clearly -
  it **never** silently falls back to clearnet.
- Strongest setup: run inside **Whonix Workstation** - Tor enforced at
  the gateway level.

Honest note: Tor hides your IP from sites, but no script can promise
"100% untraceable". This mode goes as far as a tool can.

## Interface

- Full ANSI-color TUI: colored banner, progress bars with ETA. Degrades
  cleanly when piped (`NO_COLOR=1` also respected).
- **Runtime opacity:** the running tool never reveals its sources — no
  engine names, no directory names in progress bars, result labels,
  summaries, or exports. You see counts, scores, and results; the
  machinery stays inside the code.
- GitHub profile as a **clickable terminal hyperlink** (OSC 8) in the
  header, footer, and `[G]` menu entry — plain URL fallback where
  hyperlinks aren't supported: https://github.com/karansoni0x

## Security audit (deep VAPT pass, v2.5–v2.6)

- Header-injection guard: CR/LF rejected in Tor-mode URLs.
- Redirects restricted to http/https only (Tor mode **and** clearnet —
  `file://` redirect attacks blocked).
- Full response bodies capped at 10 MB (chunked reads — no OOM).
- Selection ranges capped (no range-bomb DoS on self).
- Unicode-digit crash fixed (`²`.isdigit() trap).
- SOCKS5 handshake uses exact-length reads; overlong hostnames rejected.
- Bad ports in redirect URLs → clean OSError, never traceback.
- `seeds.json` / `countries.json` parse errors handled gracefully.
- Ctrl+D (EOF) anywhere → clean back/exit, never traceback.
- Subprocess calls use argument lists (no shell), URLs regex-validated.
- TLS certificate verification enabled (default context).
- No phoning home, no analytics, no exfiltration — the tool only
  talks to the sources it lists, when you tell it to hunt.

## Disclaimer

Research and defensive OSINT use only - threat-intel monitoring,
incident response, and academic study. The authors do not operate,
endorse, or facilitate any of the listed services. Know your local laws.

## License

MIT - see [LICENSE](LICENSE).
