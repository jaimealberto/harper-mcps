# harper-mcps

> [Versión en español](README.md)

A collection of MCP (Model Context Protocol) servers for [Claude Code](https://claude.ai/code) to manage infrastructure, access Obsidian vaults, administer Windows machines, and perform OSINT research.

Built for a self-hosted homelab. All servers use stdio transport without FastMCP for fast startup (<20ms).

## Servers

| Server | Tools | Dependencies |
|--------|-------|--------------|
| `mcp_obsidian_server.py` | search, read, write, list, tags, backlinks, structure | `mcp` |
| `mcp_ssh_server.py` | ssh_run, ssh_read/write_file, ssh_check, nmap_discover/scan/audit | `nmap` (system) |
| `mcp_winrm_server.py` | winrm_run_ps, winrm_read/write_file, winrm_install, winrm_check | `pywinrm` |
| `mcp_osint_server.py` | username, email, social, domain, whois, dns, phone, ip, breach, dossier | see below |

---

## Quick setup

### 1. Clone the repo

```bash
git clone https://github.com/JaimeAlberto/harper-mcps.git
cd harper-mcps
```

### 2. Install dependencies

**Obsidian MCP:**
```bash
pip install mcp
```

**SSH + nmap MCP:**
```bash
# No Python deps — uses system ssh and nmap
sudo apt install nmap   # or brew install nmap
```

**WinRM MCP:**
```bash
pip install pywinrm urllib3
```

**OSINT MCP:**
```bash
pip install python-whois dnspython phonenumbers
# Optional (for deeper searches):
pip install maigret holehe sherlock-project theHarvester
```

### 3. Configure

Copy the example files:
```bash
cp .env.example .env
# Edit .env with your paths

cp winrm_hosts.example.json ~/.claude/winrm_hosts.json
chmod 600 ~/.claude/winrm_hosts.json
# Edit with your Windows hosts and credentials
```

### 4. Add to Claude Code

Add to `~/.claude.json` under `mcpServers` (or use `claude mcp add`):

```json
{
  "mcpServers": {
    "harper-obsidian": {
      "type": "stdio",
      "command": "python3",
      "args": ["/path/to/harper-mcps/mcp_obsidian_server.py"],
      "env": {
        "OBSIDIAN_VAULT": "/home/youruser/Obsidian"
      }
    }
  }
}
```

See `claude_settings_example.json` for all four servers.

---

## Server details

### Obsidian MCP (`harper-obsidian`)

Gives Claude Code direct access to your [Obsidian](https://obsidian.md) vault.

**Environment variables:**
| Variable | Default | Description |
|----------|---------|-------------|
| `OBSIDIAN_VAULT` | `~/Obsidian` | Path to your vault |

**Example usage:**
- "Search my vault for notes about Python"
- "Read the note at Projects/my-project.md"
- "List all notes tagged #todo"
- "Show me all backlinks to the weekly-review note"

---

### SSH + nmap MCP (`harper-ssh`)

Run commands on remote Linux/Unix hosts via SSH and scan networks with nmap.
Reads host configuration from `~/.ssh/config` — no credentials stored anywhere.

**Features:**
- Auto-backup before writing files (creates `file.harper.YYYY-MM-DD`)
- Detects write operations and backs up the target file automatically
- nmap ping scan, port scan and full service audit

**Example usage:**
- "List my SSH hosts"
- "Run `df -h` on server01"
- "Scan ports 22,80,443 on 192.168.1.0/24"
- "Check which hosts in my network are online"

---

### WinRM MCP (`harper-winrm`)

Administer Windows machines remotely via WinRM (Windows Remote Management).

**Requirements on the Windows side:**
```powershell
# Run as Administrator on the Windows machine:
Enable-PSRemoting -Force
winrm set winrm/config/listener?Address=*+Transport=HTTPS @{Port="5986"; CertificateThumbprint="YOUR_CERT_THUMBPRINT"}
```

**Credentials file** (`~/.claude/winrm_hosts.json`, chmod 600):
```json
{
  "hosts": {
    "my-pc": {
      "endpoint": "https://192.168.1.100:5986/wsman",
      "username": "administrator",
      "password": "your-password",
      "transport": "basic",
      "server_cert_validation": "ignore",
      "message_encryption": "never"
    }
  }
}
```

**Environment variables:**
| Variable | Default | Description |
|----------|---------|-------------|
| `WINRM_HOSTS_CONFIG` | `~/.claude/winrm_hosts.json` | Path to credentials file |

**Example usage:**
- "Check if my-pc is reachable"
- "Run `winget upgrade` on my-pc and show pending updates"
- "Install Mozilla.Firefox on my-pc via winget"
- "Read C:\Users\user\AppData\Local\app\config.ini from my-pc"

---

### OSINT MCP (`harper-osint`)

OSINT research tools integrated into Claude Code. Wraps maigret, holehe, sherlock, theHarvester and standard libraries.

**Environment variables:**
| Variable | Default | Description |
|----------|---------|-------------|
| `OSINT_VAULT` | `~/osint-reports` | Directory to save reports |
| `THEHARVESTER_BIN` | auto-detect | Path to theHarvester binary |

**Tool overview:**

| Tool | What it does | Requires |
|------|-------------|----------|
| `osint_status` | Check installed tools | — |
| `osint_username` | Username on 3000+ sites (Maigret) | `pip install maigret` |
| `osint_email` | Email on 120+ services (Holehe) | `pip install holehe` |
| `osint_social_scan` | Username on 400+ socials (Sherlock) | `pip install sherlock-project` |
| `osint_domain` | Emails/subdomains/IPs (TheHarvester) | `pip install theHarvester` |
| `osint_whois` | WHOIS for domain or IP | `pip install python-whois` |
| `osint_dns` | Full DNS + SPF/DMARC/DKIM check | `pip install dnspython` |
| `osint_phone` | Country/operator/type for a number | `pip install phonenumbers` |
| `osint_ip` | ASN/geo/abuse for a public IP | — (uses ipinfo.io) |
| `osint_breach_check` | Email in HIBP data breaches | — (API key optional) |
| `osint_dossier` | Full report combining all tools | depends on target type |

**Example usage:**
- "Check osint_status to see what's installed"
- "Run osint_whois on example.com"
- "Do a full DNS analysis of company.com"
- "Check if john@example.com appears in data breaches"
- "Generate a full dossier on the domain competitor.com"

---

## Security notes

- **SSH MCP:** No credentials stored — relies entirely on `~/.ssh/config` and SSH keys.
- **WinRM MCP:** Credentials stored in `winrm_hosts.json` outside the repo. Keep it `chmod 600` and never commit it.
- **OSINT MCP:** All tools make outbound network requests. Be aware of rate limits and terms of service.
- **nmap:** Some scan types require root. The servers use `-sT` (TCP connect) which works without root.

---

## License

MIT. Use at your own risk. These tools make real network connections and can affect remote systems.
