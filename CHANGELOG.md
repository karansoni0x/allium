# Changelog

All notable changes to Allium are documented here. Version numbers match
the GitHub releases exactly — what the release says is what the code does.

## v2.7.1 — 2026-11-06

Live onion discovery for OSINT and threat-intel research. Every source is
queried live, no stale static lists.

- 31 live sources: 4 directories + 27 search engines, queried live on
  every hunt (25 onion-only engines via Tor + Ahmia and Torch on clearnet)
- Ransomware leak-site tracking, live from ransomware.live group profiles
- Tor fail-closed stealth: traffic via Tor SOCKS5h, DNS resolved by Tor,
  never falls back to clearnet silently
- Strict keyword filtering and corroboration-ranked results, every result
  explained
- 197-country guided flow, multi-select and ranges
- Zero dependencies, Python 3 stdlib only
- Export in JSON, Markdown, CSV and TXT
- Security hardening from the v2.5–v2.7 audit, including the stealth IP
  leak fix and Tor verification

This release is the v2.7 codebase with the version aligned to the release
tag — no behaviour change from v2.7.

## v2.7 — 2026-10-31

Hostile-input hardening (external security review — every claim verified
against the code, all real findings fixed):

- **Stealth IP leak fixed (critical):** the startup health check probed
  6 clearnet sites via plain urllib even with stealth ON. Now probes
  through Tor when stealth is on.
- **Tor verified, not just detected:** confirmed via
  `check.torproject.org/api/ip` (`IsTor: true`); otherwise warns
  "proxy NOT confirmed as Tor".
- **Latent decode crash fixed:** `.decode("utf-8", "errors")` used an
  invalid error-handler name — raised `LookupError` on non-UTF-8 pages
  (e.g. cp1251 Russian forums). Now `"replace"`.
- **Slow-drip DoS fixed:** overall request deadline in Tor fetches.
- **Terminal injection fixed:** control chars stripped from
  remote-sourced names (ANSI/OSC injection via `&#27;`).
- **CSV formula injection fixed:** cells starting with `= + - @`
  neutralized; Markdown table pipes escaped.
- **Redirect SSRF blocked:** clearnet redirects to private/loopback/
  link-local IPs refused (resolved + checked via `ipaddress`).
- **DoS hardening:** chunked decoder is now linear (list+join); engine
  pages truncated to 2 MB before regex parsing.
- **Host header:** non-default ports now included.

## v2.6 — 2026-10-19

- Precision strict-gate across engine + seed rows
- Runtime opacity: no source/engine names in user-visible output
- Parallel engine queries (8 workers)

## v2.5 — 2026-10-19

- 27 live search engines (Ahmia + Torch + 25 onion engines)
- Original deep VAPT pass (see README Security audit section)

## v2.4 — 2026-10-19

- ANSI colors, boxed banner, author + clickable GitHub link

## v2.3 — 2026-10-19

- Country-specific flow (197 countries, region → country → types)

## v2.2 — 2026-10-19

- Full-English UI, ETA progress bars

## v2.1 — 2026-10-18

- Tor fail-closed stealth mode (SOCKS5h, remote DNS)

## v2.0 — 2026-10-18

- Multi-select + ranges, skip-list blocklist, keyword refine

## v1.0 — 2026-10-18

- 4 live directories + ransomware.live extraction (409 groups → 848 DLS
  onions), menu-driven, zero dependencies
