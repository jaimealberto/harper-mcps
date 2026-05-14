#!/usr/bin/env python3
"""
MCP server for OSINT research on people, companies and infrastructure.

Configure via environment variables:
  OSINT_VAULT      — directory to save reports (default: ~/osint-reports)
  THEHARVESTER_BIN — path to theHarvester binary (default: auto-detect via PATH)

Tools:
  osint_status        — check installed tools
  osint_username      — Maigret: username on 3000+ sites
  osint_email         — Holehe: email on 120+ platforms
  osint_social_scan   — Sherlock: username on 400+ social networks
  osint_domain        — TheHarvester: emails/subdomains/employees from a domain
  osint_whois         — WHOIS for domain or IP
  osint_dns           — full DNS analysis + SPF/DMARC check
  osint_phone         — country/operator/type for a phone number
  osint_ip            — ASN/org/geo/abuse for an IP address
  osint_breach_check  — HaveIBeenPwned: email in known breaches
  osint_dossier       — full dossier on a target (saves to OSINT_VAULT)

MCP over stdio without FastMCP (startup <20ms).
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

# Configure via environment variables
VAULT_OSINT = Path(os.environ.get("OSINT_VAULT", str(Path.home() / "osint-reports")))
VAULT_OSINT.mkdir(parents=True, exist_ok=True)

TIMEOUT_FAST   = 60
TIMEOUT_MEDIUM = 180
TIMEOUT_SLOW   = 600

# theHarvester: auto-detect via PATH first, then env var override
_theharvester_env = os.environ.get("THEHARVESTER_BIN", "")
if _theharvester_env:
    THEHARVESTER_BIN = Path(_theharvester_env)
else:
    _detected = shutil.which("theHarvester")
    THEHARVESTER_BIN = Path(_detected) if _detected else Path("theHarvester")

# Add current interpreter's bin dir to PATH so tools installed in the same
# conda/venv environment are discoverable
_py_bin = str(Path(sys.executable).parent)
if _py_bin not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _py_bin + ":" + os.environ.get("PATH", "")


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _run(*args, timeout: int = 60, input_text: Optional[str] = None) -> Tuple[int, str, str]:
    try:
        r = subprocess.run(
            list(args), capture_output=True, text=True,
            timeout=timeout, input=input_text,
        )
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"TIMEOUT ({timeout}s)"
    except FileNotFoundError:
        return -2, "", f"Tool not found: {args[0]}"
    except Exception as e:
        return -3, "", str(e)


def _has(tool: str) -> bool:
    return shutil.which(tool) is not None


def _has_lib(module: str) -> bool:
    try:
        __import__(module)
        return True
    except ImportError:
        return False


def _save_vault(filename: str, content: str) -> Path:
    path = VAULT_OSINT / filename
    path.write_text(content, encoding="utf-8")
    return path


# ─────────────────────────────────────────────────────────────────────────────
# Tool: osint_status
# ─────────────────────────────────────────────────────────────────────────────

def tool_osint_status(_args: dict) -> str:
    cli_map = {
        "maigret":      "pip install maigret",
        "holehe":       "pip install holehe",
        "sherlock":     "pip install sherlock-project",
        "theHarvester": str(THEHARVESTER_BIN),
        "whois":        "(system)",
    }
    lib_map = {
        "whois":        "pip install python-whois",
        "dns":          "pip install dnspython",
        "phonenumbers": "pip install phonenumbers",
    }

    lines = ["=== Harper OSINT Tools Status ===", ""]
    lines.append("CLI tools:")
    for tool, install in cli_map.items():
        if tool == "theHarvester":
            ok = THEHARVESTER_BIN.exists() or _has("theHarvester")
        else:
            ok = _has(tool)
        status = "✓ installed" if ok else f"✗ not installed  → {install}"
        lines.append(f"  {tool:<20} {status}")
    lines.append("")
    lines.append("Python libraries:")
    for mod, install in lib_map.items():
        status = "✓ installed" if _has_lib(mod) else f"✗ not installed  → {install}"
        lines.append(f"  {mod:<20} {status}")
    lines.append("")
    lines.append(f"Reports directory: {VAULT_OSINT}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Tool: osint_username  (Maigret)
# ─────────────────────────────────────────────────────────────────────────────

def tool_osint_username(args: dict) -> str:
    username = args["username"]
    limit    = args.get("limit", 500)
    save     = args.get("save_report", True)

    if not _has("maigret"):
        return "ERROR: maigret not installed. Run: pip install maigret"

    json_out = VAULT_OSINT / f"report_{username}_simple.json"

    cmd = ["maigret", username, "--top-sites", str(limit), "--no-color", "--no-progressbar"]
    if save:
        cmd += ["--json", "simple", "--folderoutput", str(VAULT_OSINT)]

    rc, stdout, stderr = _run(*cmd, timeout=TIMEOUT_MEDIUM)
    output = (stdout + stderr).strip()

    if save and json_out.exists():
        try:
            data = json.loads(json_out.read_text())
            found = []
            for site, info in data.items():
                if not isinstance(info, dict):
                    continue
                status = info.get("status", {})
                msg = status.get("message", "") if isinstance(status, dict) else str(status)
                if msg in ("Claimed", "Found"):
                    url = info.get("url_user", info.get("url", ""))
                    found.append(f"  [+] {site:<30} {url}")
            summary = f"Found on {len(found)} sites:\n\n" + "\n".join(found[:60])
            if len(found) > 60:
                summary += f"\n  ... and {len(found)-60} more in {json_out}"
            return f"=== Maigret: @{username} ===\n\n{summary}\n\nJSON: {json_out}"
        except Exception:
            pass

    found_lines = [l for l in output.splitlines() if "[+]" in l or "Found" in l.lower()]
    return (
        f"=== Maigret: @{username} ===\n\n"
        + ("\n".join(found_lines[:60]) if found_lines else output[:3000])
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tool: osint_email  (Holehe)
# ─────────────────────────────────────────────────────────────────────────────

def tool_osint_email(args: dict) -> str:
    email = args["email"]

    if not _has("holehe"):
        return "ERROR: holehe not installed. Run: pip install holehe"

    rc, stdout, stderr = _run(
        "holehe", email, "--no-color", "--only-used",
        timeout=TIMEOUT_MEDIUM,
    )
    output = (stdout + stderr).strip()
    if not output:
        return f"No results for {email} — possibly no registrations or network error."

    found   = [l for l in output.splitlines() if "[+]" in l]
    unknown = [l for l in output.splitlines() if "[?]" in l]
    header  = f"=== Holehe: {email} ===\n\nRegistered on {len(found)} service(s)"
    if unknown:
        header += f" ({len(unknown)} unconfirmed)"
    return header + ":\n\n" + "\n".join(found + unknown)


# ─────────────────────────────────────────────────────────────────────────────
# Tool: osint_social_scan  (Sherlock)
# ─────────────────────────────────────────────────────────────────────────────

def tool_osint_social_scan(args: dict) -> str:
    username = args["username"]
    timeout  = args.get("timeout_per_site", 10)

    if not _has("sherlock"):
        return "ERROR: sherlock not installed. Run: pip install sherlock-project"

    rc, stdout, stderr = _run(
        "sherlock", username,
        "--print-found", "--no-color",
        "--timeout", str(timeout),
        timeout=TIMEOUT_FAST,
    )
    output = stdout.strip()
    found  = [l for l in output.splitlines() if "[+]" in l]
    missed = output.count("[-]")

    return (
        f"=== Sherlock: @{username} ===\n"
        f"Found on {len(found)} platforms (no result ~{missed}):\n\n"
        + "\n".join(found)
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tool: osint_domain  (TheHarvester)
# ─────────────────────────────────────────────────────────────────────────────

def tool_osint_domain(args: dict) -> str:
    domain  = args["domain"]
    sources = args.get("sources", "duckduckgo,yahoo,hackertarget,crtsh,rapiddns,urlscan")
    limit   = args.get("limit", 200)

    if not (THEHARVESTER_BIN.exists() or _has("theHarvester")):
        return (
            f"ERROR: theHarvester not found.\n"
            f"Install: pip install theHarvester\n"
            f"Or set THEHARVESTER_BIN env var to the binary path."
        )

    bin_path = str(THEHARVESTER_BIN) if THEHARVESTER_BIN.exists() else "theHarvester"
    rc, stdout, stderr = _run(
        bin_path,
        "-d", domain,
        "-b", sources,
        "-l", str(limit),
        timeout=TIMEOUT_SLOW,
    )
    output = (stdout + stderr).strip()
    return f"=== TheHarvester: {domain} ===\n\n{output[:6000]}"


# ─────────────────────────────────────────────────────────────────────────────
# Tool: osint_whois
# ─────────────────────────────────────────────────────────────────────────────

def tool_osint_whois(args: dict) -> str:
    target = args["target"]

    if _has_lib("whois"):
        try:
            import whois as _whois
            w = _whois.whois(target)
            lines = [f"=== WHOIS: {target} ===", ""]
            fields = [
                ("Domain",       ["domain_name"]),
                ("Registrant",   ["org", "registrant_name", "name"]),
                ("Email(s)",     ["emails", "registrant_email"]),
                ("Country",      ["registrant_country", "country"]),
                ("State/Prov",   ["registrant_state_province"]),
                ("Registrar",    ["registrar"]),
                ("Registrar URL",["registrar_url"]),
                ("Created",      ["creation_date"]),
                ("Expires",      ["expiration_date"]),
                ("Updated",      ["updated_date"]),
                ("Nameservers",  ["name_servers"]),
                ("Status",       ["status"]),
                ("DNSSEC",       ["dnssec"]),
            ]
            for label, keys in fields:
                val = None
                for key in keys:
                    val = w.get(key) if hasattr(w, "get") else getattr(w, key, None)
                    if val:
                        break
                if val:
                    if isinstance(val, list):
                        val = ", ".join(str(v) for v in val[:5])
                    lines.append(f"  {label:<15} {val}")
            if len(lines) <= 2:
                for k, v in (w.items() if hasattr(w, "items") else vars(w).items()):
                    if v:
                        lines.append(f"  {k:<20} {v}")
            return "\n".join(lines)
        except Exception:
            pass

    # Fallback: system whois binary
    rc, stdout, stderr = _run("whois", target, timeout=30)
    if rc == 0 and stdout:
        relevant = {"registrant", "registrar", "creation", "expir", "updated", "name server",
                    "dnssec", "status", "email", "org", "netname", "descr", "country", "abuse"}
        lines = [f"=== WHOIS: {target} ===", ""]
        for line in stdout.splitlines():
            l = line.strip().lower()
            if l and not l.startswith("%") and not l.startswith("#"):
                if any(k in l for k in relevant):
                    lines.append(f"  {line.strip()}")
        return "\n".join(lines) or f"=== WHOIS: {target} ===\n\n{stdout[:3000]}"

    return f"ERROR: WHOIS failed for {target} — install python-whois: pip install python-whois"


# ─────────────────────────────────────────────────────────────────────────────
# Tool: osint_dns
# ─────────────────────────────────────────────────────────────────────────────

def tool_osint_dns(args: dict) -> str:
    domain = args["domain"]

    if not _has_lib("dns"):
        return "ERROR: dnspython not installed. Run: pip install dnspython"

    import dns.resolver
    import dns.exception

    resolver = dns.resolver.Resolver()
    resolver.timeout  = 5
    resolver.lifetime = 10

    lines = [f"=== DNS: {domain} ===", ""]

    for rtype in ["A", "AAAA", "MX", "NS", "TXT", "SOA", "CNAME"]:
        try:
            answers = resolver.resolve(domain, rtype)
            vals = [str(r) for r in answers]
            lines.append(f"  {rtype:<8} {vals[0]}")
            for v in vals[1:]:
                lines.append(f"  {'':8} {v}")
        except Exception:
            pass

    lines += ["", "--- Email security ---"]
    try:
        txts = resolver.resolve(domain, "TXT")
        spf = [str(r) for r in txts if "v=spf1" in str(r)]
        lines.append(f"  SPF:    {'✓ ' + spf[0][:100] if spf else '✗ not configured'}")
    except Exception:
        lines.append("  SPF:    (error querying)")

    try:
        dmarc = resolver.resolve(f"_dmarc.{domain}", "TXT")
        dmarc_v = [str(r) for r in dmarc if "DMARC1" in str(r).upper()]
        lines.append(f"  DMARC:  {'✓ ' + dmarc_v[0][:100] if dmarc_v else '✗ not configured'}")
    except Exception:
        lines.append("  DMARC:  ✗ not configured")

    for sel in ["default", "google", "k1", "mail", "s1", "selector1"]:
        try:
            dkim = resolver.resolve(f"{sel}._domainkey.{domain}", "TXT")
            lines.append(f"  DKIM:   ✓ selector '{sel}' active")
            break
        except Exception:
            pass
    else:
        lines.append("  DKIM:   (standard selectors not found)")

    lines += ["", "--- Common subdomains ---"]
    subdomains = ["www", "mail", "smtp", "ftp", "vpn", "remote", "api",
                  "dev", "staging", "admin", "webmail", "autodiscover", "autoconfig"]
    for sub in subdomains:
        try:
            ans = resolver.resolve(f"{sub}.{domain}", "A")
            ip = str(list(ans)[0])
            lines.append(f"  {sub:<15} {ip}")
        except Exception:
            pass

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Tool: osint_phone
# ─────────────────────────────────────────────────────────────────────────────

def tool_osint_phone(args: dict) -> str:
    phone   = args["phone"]
    country = args.get("country", "US")

    if not _has_lib("phonenumbers"):
        return "ERROR: phonenumbers not installed. Run: pip install phonenumbers"

    import phonenumbers
    from phonenumbers import geocoder, carrier, number_type, PhoneNumberType, timezone

    try:
        parsed = phonenumbers.parse(phone, country)
    except Exception as e:
        return f"ERROR: invalid number '{phone}' — {e}\nUse format +12125551234 or local with country='US'"

    valid    = phonenumbers.is_valid_number(parsed)
    possible = phonenumbers.is_possible_number(parsed)
    e164     = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    intl     = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
    national = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.NATIONAL)

    type_names = {
        PhoneNumberType.MOBILE:               "Mobile",
        PhoneNumberType.FIXED_LINE:           "Fixed line",
        PhoneNumberType.FIXED_LINE_OR_MOBILE: "Fixed or Mobile",
        PhoneNumberType.VOIP:                 "VoIP",
        PhoneNumberType.TOLL_FREE:            "Toll-free",
        PhoneNumberType.PREMIUM_RATE:         "Premium rate",
        PhoneNumberType.SHARED_COST:          "Shared cost",
        PhoneNumberType.PERSONAL_NUMBER:      "Personal number",
        PhoneNumberType.PAGER:                "Pager",
        PhoneNumberType.UAN:                  "UAN",
        PhoneNumberType.UNKNOWN:              "Unknown",
    }
    ntype   = number_type(parsed)
    geo     = geocoder.description_for_number(parsed, "en")
    carr    = carrier.name_for_number(parsed, "en")
    tzones  = timezone.time_zones_for_number(parsed)

    lines = [f"=== Phone: {phone} ===", ""]
    lines += [
        f"  E.164:        {e164}",
        f"  International:{intl}",
        f"  National:     {national}",
        f"  Valid:        {'✓ Yes' if valid else '✗ No'}",
        f"  Possible:     {'✓ Yes' if possible else '✗ No'}",
        f"  Type:         {type_names.get(ntype, 'Unknown')}",
        f"  Country/Region:{geo or 'Unknown'}",
        f"  Carrier:      {carr or 'Not available (may have ported)'}",
        f"  Country code: +{parsed.country_code}",
        f"  National:     {parsed.national_number}",
        f"  Timezone(s):  {', '.join(tzones) if tzones else 'Unknown'}",
    ]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Tool: osint_ip
# ─────────────────────────────────────────────────────────────────────────────

def tool_osint_ip(args: dict) -> str:
    ip = args["ip"]

    lines = [f"=== IP: {ip} ===", ""]

    # ipinfo.io (no key needed: 50k req/month free)
    try:
        import urllib.request as _req
        with _req.urlopen(f"https://ipinfo.io/{ip}/json", timeout=10) as r:
            data = json.loads(r.read())
        field_map = [
            ("IP",        "ip"),
            ("Hostname",  "hostname"),
            ("City",      "city"),
            ("Region",    "region"),
            ("Country",   "country"),
            ("Org/ASN",   "org"),
            ("Location",  "loc"),
            ("Timezone",  "timezone"),
            ("Postal",    "postal"),
        ]
        for label, key in field_map:
            if key in data:
                lines.append(f"  {label:<12} {data[key]}")
        if "bogon" in data:
            lines.append(f"  Bogon:       {data['bogon']} (private/reserved IP)")
    except Exception as e:
        lines.append(f"  [ipinfo.io] Error: {e}")

    lines += ["", "--- IP WHOIS ---"]
    rc, stdout, _ = _run("whois", ip, timeout=15)
    if rc == 0 and stdout:
        relevant = {"netname", "descr", "org-name", "orgname", "country",
                    "abuse-mailbox", "aut-num", "route", "cidr", "netrange"}
        seen = set()
        for line in stdout.splitlines():
            key = line.split(":")[0].strip().lower() if ":" in line else ""
            if key in relevant and key not in seen:
                lines.append(f"  {line.strip()}")
                seen.add(key)

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Tool: osint_breach_check  (HaveIBeenPwned v3)
# ─────────────────────────────────────────────────────────────────────────────

def tool_osint_breach_check(args: dict) -> str:
    email   = args["email"]
    api_key = args.get("api_key", "")

    import urllib.request as _req
    import urllib.error

    headers = {"User-Agent": "MCP-OSINT/1.0"}
    if api_key:
        headers["hibp-api-key"] = api_key

    url = f"https://haveibeenpwned.com/api/v3/breachedaccount/{email}?truncateResponse=false"
    req = _req.Request(url, headers=headers)

    try:
        with _req.urlopen(req, timeout=15) as r:
            breaches = json.loads(r.read())
        lines = [f"=== HaveIBeenPwned: {email} ===", "",
                 f"  ⚠ Found in {len(breaches)} known breach(es):", ""]
        for b in sorted(breaches, key=lambda x: x.get("BreachDate", ""), reverse=True):
            classes = ", ".join(b.get("DataClasses", [])[:6])
            lines.append(f"  [{b.get('BreachDate','?')}] {b['Name']:<30} Data: {classes}")
        return "\n".join(lines)

    except urllib.error.HTTPError as e:
        if e.code == 404:
            return f"=== HaveIBeenPwned: {email} ===\n\n  ✓ Not found in any known breach."
        if e.code == 401:
            return (
                "ERROR 401: HIBP API key required.\n"
                "Get one at https://haveibeenpwned.com/API/Key\n"
                "Pass it as parameter: api_key='your-key'"
            )
        if e.code == 429:
            return "ERROR 429: Rate limit. Wait 1 minute and try again."
        return f"ERROR HTTP {e.code}: {e.reason}"
    except Exception as e:
        return f"ERROR: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# Tool: osint_dossier
# ─────────────────────────────────────────────────────────────────────────────

def tool_osint_dossier(args: dict) -> str:
    """
    Full dossier on a target. Combines multiple tools and saves to OSINT_VAULT.
    target_type: 'person' | 'email' | 'company' | 'domain' | 'ip' | 'phone'
    """
    target      = args["target"]
    target_type = args.get("target_type", "domain")
    save        = args.get("save", True)

    ts   = datetime.now().strftime("%Y-%m-%d %H:%M")
    slug = "".join(c if c.isalnum() or c in "-_." else "_" for c in target)
    filename = f"{datetime.now().strftime('%Y-%m-%d')}_{target_type}_{slug}.md"

    sections = [
        f"# OSINT Dossier: `{target}`",
        f"**Type:** {target_type}  |  **Date:** {ts}  |  **Generated by:** MCP OSINT",
        "",
    ]

    def _section(title: str, content: str):
        sections.append(f"## {title}")
        sections.append(content)
        sections.append("")

    if target_type == "person":
        _section("Sherlock — Social networks (fast)", tool_osint_social_scan({"username": target}))
        _section("Maigret — Extended search (3000+ sites)", tool_osint_username({"username": target, "limit": 500, "save_report": True}))

    elif target_type == "email":
        _section("Registered services (Holehe)", tool_osint_email({"email": target}))
        _section("Data breaches (HIBP)", tool_osint_breach_check({"email": target}))
        domain = target.split("@")[-1] if "@" in target else None
        if domain:
            _section(f"WHOIS for {domain}", tool_osint_whois({"target": domain}))
            _section(f"DNS for {domain}", tool_osint_dns({"domain": domain}))

    elif target_type in ("company", "domain"):
        _section("WHOIS", tool_osint_whois({"target": target}))
        _section("DNS + Email security", tool_osint_dns({"domain": target}))
        _section("Public data collection (TheHarvester)", tool_osint_domain({"domain": target}))

    elif target_type == "ip":
        _section("IP information", tool_osint_ip({"ip": target}))

    elif target_type == "phone":
        _section("Phone analysis", tool_osint_phone({"phone": target}))

    else:
        sections.append(f"ERROR: target_type '{target_type}' not recognized.")
        sections.append("Valid values: person | email | company | domain | ip | phone")

    content = "\n\n".join(sections)

    if save:
        path = _save_vault(filename, content)
        preview = content[:1500] + ("\n\n[... see full report in vault ...]" if len(content) > 1500 else "")
        return f"Dossier saved to: {path}\n\n---\n\n{preview}"

    return content


# ─────────────────────────────────────────────────────────────────────────────
# Tool registry
# ─────────────────────────────────────────────────────────────────────────────

TOOLS = {
    "osint_status": {
        "fn": tool_osint_status,
        "description": (
            "Check which OSINT tools are installed "
            "(maigret, holehe, sherlock, theHarvester, python-whois, dnspython, phonenumbers). "
            "Shows installation command for missing ones."
        ),
        "inputSchema": {
            "type": "object", "properties": {},
            "title": "osint_status",
        },
    },
    "osint_username": {
        "fn": tool_osint_username,
        "description": (
            "Search for a username on 3000+ websites using Maigret. "
            "Extracts profile URLs, found personal data and alternative usernames. "
            "Saves JSON report to OSINT_VAULT. Takes 1-3 minutes depending on site limit."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "username":     {"type": "string", "description": "Username to investigate"},
                "limit":        {"type": "integer", "description": "Sites to check (default 500, max 3000)"},
                "save_report":  {"type": "boolean", "description": "Save JSON to vault (default true)"},
            },
            "required": ["username"],
            "title": "osint_username",
        },
    },
    "osint_email": {
        "fn": tool_osint_email,
        "description": (
            "Check which online services an email is registered on using Holehe (120+ platforms). "
            "Uses password recovery — does not create accounts or leave traces. "
            "Useful for: finding what services a person uses, validating if an email is active."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "email": {"type": "string", "description": "Email address to investigate"},
            },
            "required": ["email"],
            "title": "osint_email",
        },
    },
    "osint_social_scan": {
        "fn": tool_osint_social_scan,
        "description": (
            "Fast username search on 400+ social networks using Sherlock. "
            "Faster than Maigret but less thorough — ideal as a first step. "
            "Returns list of URLs where the username exists."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "username":         {"type": "string", "description": "Username to search"},
                "timeout_per_site": {"type": "integer", "description": "Timeout per site in seconds (default 10)"},
            },
            "required": ["username"],
            "title": "osint_social_scan",
        },
    },
    "osint_domain": {
        "fn": tool_osint_domain,
        "description": (
            "Gather public information from a domain using TheHarvester: "
            "corporate emails, subdomains, IPs, employee names. "
            "Sources: duckduckgo, yahoo, hackertarget, crtsh, rapiddns, urlscan. "
            "Useful for: mapping company infrastructure, finding contacts."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain":  {"type": "string", "description": "Domain to investigate (e.g. company.com)"},
                "sources": {"type": "string", "description": "Comma-separated sources (default: duckduckgo,yahoo,hackertarget,crtsh,rapiddns,urlscan)"},
                "limit":   {"type": "integer", "description": "Max results per source (default 200)"},
            },
            "required": ["domain"],
            "title": "osint_domain",
        },
    },
    "osint_whois": {
        "fn": tool_osint_whois,
        "description": (
            "WHOIS lookup for a domain or IP. Returns: registrant, organization, "
            "contact emails, creation/expiration dates, nameservers, status and DNSSEC. "
            "Useful for: identifying domain owner, registration dates, registrar."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Domain (company.com) or IP to query"},
            },
            "required": ["target"],
            "title": "osint_whois",
        },
    },
    "osint_dns": {
        "fn": tool_osint_dns,
        "description": (
            "Full DNS enumeration for a domain: A, AAAA, MX, NS, TXT, SOA, CNAME records. "
            "Analyzes email security configuration: SPF, DMARC, DKIM. "
            "Checks common subdomains (www, mail, vpn, admin, api...). "
            "Useful for: mapping infrastructure, detecting insecure email configurations."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Domain to analyze"},
            },
            "required": ["domain"],
            "title": "osint_dns",
        },
    },
    "osint_phone": {
        "fn": tool_osint_phone,
        "description": (
            "Analyze a phone number: validate E.164 format, identify country, "
            "carrier (may not be exact due to porting), line type "
            "(mobile, fixed, VoIP, premium rate), and timezone. "
            "Supports any country. Default country code is 'US'."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "phone":   {"type": "string", "description": "Phone number (e.g. +12125551234 or 2125551234)"},
                "country": {"type": "string", "description": "ISO country code for local numbers (default 'US')"},
            },
            "required": ["phone"],
            "title": "osint_phone",
        },
    },
    "osint_ip": {
        "fn": tool_osint_ip,
        "description": (
            "Get information about a public IP: ASN, organization, country, city, "
            "reverse hostname, abuse contact and network ranges. "
            "Uses ipinfo.io (no key needed, 50k req/month) + system WHOIS. "
            "Useful for: identifying IP owner, detecting VPNs/datacenters/hosting."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "ip": {"type": "string", "description": "Public IP address to investigate"},
            },
            "required": ["ip"],
            "title": "osint_ip",
        },
    },
    "osint_breach_check": {
        "fn": tool_osint_breach_check,
        "description": (
            "Check if an email appears in known data breaches using HaveIBeenPwned API v3. "
            "Without API key it works but is rate-limited. With api_key (from haveibeenpwned.com) "
            "gets full detail of each breach (date, exposed data, description). "
            "Useful for: verifying credential exposure, security awareness."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "email":   {"type": "string", "description": "Email to check"},
                "api_key": {"type": "string", "description": "HIBP API key (optional but recommended)"},
            },
            "required": ["email"],
            "title": "osint_breach_check",
        },
    },
    "osint_dossier": {
        "fn": tool_osint_dossier,
        "description": (
            "Generate a complete OSINT dossier combining multiple tools based on target type. "
            "Saves the report as Markdown to OSINT_VAULT directory. "
            "Types: 'person' (username → Sherlock+Maigret), 'email' (Holehe+HIBP+DNS), "
            "'company'/'domain' (WHOIS+DNS+TheHarvester), 'ip' (ipinfo+WHOIS), 'phone' (phonenumbers). "
            "May take several minutes for person/company targets."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target":      {"type": "string", "description": "Username, email, domain, IP or phone number"},
                "target_type": {
                    "type": "string",
                    "enum": ["person", "email", "company", "domain", "ip", "phone"],
                    "description": "Type of target",
                },
                "save": {"type": "boolean", "description": "Save to OSINT_VAULT (default true)"},
            },
            "required": ["target", "target_type"],
            "title": "osint_dossier",
        },
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# MCP stdio loop
# ─────────────────────────────────────────────────────────────────────────────

def _send(obj: dict):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def _handle(msg: dict):
    method = msg.get("method", "")
    msg_id = msg.get("id")

    if method == "initialize":
        _send({
            "jsonrpc": "2.0", "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "harper-osint", "version": "1.0"},
            },
        })

    elif method == "notifications/initialized":
        pass

    elif method == "tools/list":
        _send({
            "jsonrpc": "2.0", "id": msg_id,
            "result": {
                "tools": [
                    {"name": name, "description": spec["description"], "inputSchema": spec["inputSchema"]}
                    for name, spec in TOOLS.items()
                ],
            },
        })

    elif method == "tools/call":
        params    = msg.get("params", {})
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        if tool_name not in TOOLS:
            _send({
                "jsonrpc": "2.0", "id": msg_id,
                "error": {"code": -32601, "message": f"Tool not found: {tool_name}"},
            })
            return
        try:
            result = TOOLS[tool_name]["fn"](arguments)
        except Exception as e:
            result = f"Internal ERROR in {tool_name}: {e}"
        _send({
            "jsonrpc": "2.0", "id": msg_id,
            "result": {"content": [{"type": "text", "text": result}]},
        })

    elif msg_id is not None:
        _send({
            "jsonrpc": "2.0", "id": msg_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        })


def main():
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            continue
        _handle(msg)


if __name__ == "__main__":
    main()
