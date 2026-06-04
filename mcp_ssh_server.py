#!/usr/bin/env python3
"""
MCP server for SSH access and nmap network scanning.
Uses ~/.ssh/config to resolve hosts and keys — no stored passwords.

MCP over stdio without FastMCP (startup <20ms).

Available tools:
  ssh_list_hosts  — list configured hosts
  ssh_run         — run a command on a remote host
  ssh_read_file   — read a remote file
  ssh_write_file  — write a remote file (with auto-backup)
  ssh_check       — test connectivity
  ssh_check_all   — check all hosts at once
  nmap_discover   — ping scan to find live hosts
  nmap_scan       — port scan
  nmap_audit      — full service audit with NSE scripts
"""
import json
import re
import shlex
import subprocess
import sys
from datetime import date
from pathlib import Path

SSH_CONFIG = Path.home() / ".ssh" / "config"
SSH_OPTS = [
    "-o", "StrictHostKeyChecking=accept-new",
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=10",
]

IGNORE_PATHS = {"/dev/null", "/dev/stdin", "/dev/stdout", "/dev/stderr"}

WRITE_PATTERNS = [
    r'(?<![<2])>\s*["\']?(/[^\s"\';|&]+)',
    r'\btee\s+["\']?(/[^\s"\';|&]+)',
    r'\bsed\s+-i\S*\s+\S+\s+(/[^\s"\';|&]+)',
    r'\bcp\s+\S+\s+(/[^\s"\';|&]+)',
]

# ─────────────────────────────────────────
# SSH logic
# ─────────────────────────────────────────

def _detect_write_path(command: str):
    for pattern in WRITE_PATTERNS:
        m = re.search(pattern, command)
        if m:
            candidate = m.group(1).strip("'\"")
            if candidate.startswith("/dev/"):
                continue
            if ".harper." in candidate:
                continue
            return candidate
    return None


def _auto_backup(host: str, path: str) -> str:
    today = date.today().isoformat()
    backup_path = f"{path}.harper.{today}"
    cmd = (
        f"if test -f {path}; then "
        f"  cp {path} {backup_path} 2>/dev/null && echo BACKUP_OK || echo BACKUP_NOPERM; "
        f"else echo SKIP_NO_FILE; fi"
    )
    try:
        rc, stdout, stderr = _ssh(host, cmd, timeout=10)
        out = stdout.strip()
        if "BACKUP_OK" in out:
            return f"[backup] {host}:{backup_path}"
        elif "SKIP_NO_FILE" in out:
            return "[backup] new file, no backup needed"
        else:
            return f"[backup] WARNING: no permissions to backup {host}:{path} — requires root"
    except Exception as e:
        return f"[backup] ERROR: {e}"


def _parse_ssh_hosts() -> dict:
    hosts = {}
    current = None
    skip = {"*", "github.com"}
    for line in SSH_CONFIG.read_text().splitlines():
        line = line.strip()
        if line.startswith("Host "):
            alias = line[5:].strip()
            if alias not in skip:
                current = alias
                hosts[current] = {}
            else:
                current = None
        elif current and "=" not in line and " " in line:
            key, _, val = line.partition(" ")
            hosts[current][key.lower()] = val.strip()
    return hosts


def _ssh(host: str, command: str, timeout: int = 30):
    result = subprocess.run(
        ["ssh"] + SSH_OPTS + [host, command],
        capture_output=True, text=True, timeout=timeout
    )
    return result.returncode, result.stdout, result.stderr


def _fmt(rc: int, stdout: str, stderr: str) -> str:
    out = stdout.rstrip()
    err = stderr.rstrip()
    if rc == 0:
        return out if out else "(no output)"
    return f"ERROR (rc={rc})\n{err or out or '(no output)'}"


# ─────────────────────────────────────────
# Tool implementations
# ─────────────────────────────────────────

def tool_ssh_list_hosts(_args: dict) -> str:
    hosts = _parse_ssh_hosts()
    lines = []
    for alias, info in sorted(hosts.items()):
        user = info.get("user", "?")
        hostname = info.get("hostname", "?")
        port = info.get("port", "22")
        port_str = f":{port}" if port != "22" else ""
        lines.append(f"  {alias:<30} {user}@{hostname}{port_str}")
    return f"{len(hosts)} hosts available:\n\n" + "\n".join(lines)


def tool_ssh_run(args: dict) -> str:
    host = args["host"]
    command = args["command"]
    timeout = args.get("timeout", 30)
    backup_note = ""
    write_path = _detect_write_path(command)
    if write_path:
        backup_note = _auto_backup(host, write_path) + "\n"
    try:
        rc, stdout, stderr = _ssh(host, command, timeout)
        return backup_note + _fmt(rc, stdout, stderr)
    except subprocess.TimeoutExpired:
        return f"TIMEOUT ({timeout}s) — host {host} not responding or command too slow."
    except Exception as e:
        return f"SSH ERROR: {e}"


def tool_ssh_read_file(args: dict) -> str:
    host = args["host"]
    path = args["path"]
    try:
        rc, stdout, stderr = _ssh(host, f"cat {shlex.quote(path)}")
        if rc != 0:
            return f"Could not read {path} on {host}: {stderr.strip()}"
        return f"# {host}:{path}\n\n{stdout}"
    except subprocess.TimeoutExpired:
        return f"TIMEOUT — {host} not responding."
    except Exception as e:
        return f"ERROR: {e}"


def tool_ssh_write_file(args: dict) -> str:
    host = args["host"]
    path = args["path"]
    content = args["content"]
    backup = args.get("backup", True)
    steps = []
    try:
        if backup:
            steps.append(_auto_backup(host, path))
        import base64
        b64 = base64.b64encode(content.encode()).decode()
        write_cmd = f"echo '{b64}' | base64 -d > {shlex.quote(path)} && echo WRITTEN"
        rc, stdout, stderr = _ssh(host, write_cmd)
        if "WRITTEN" in stdout:
            steps.append(f"Written: {path} ({len(content)} bytes)")
        else:
            steps.append(f"ERROR writing: {stderr.strip() or stdout.strip()}")
        return "\n".join(steps)
    except subprocess.TimeoutExpired:
        return f"TIMEOUT — {host} not responding."
    except Exception as e:
        return f"ERROR: {e}"


def tool_ssh_check(args: dict) -> str:
    host = args["host"]
    try:
        rc, stdout, stderr = _ssh(host, "echo OK && hostname && uptime", timeout=12)
        if rc == 0:
            return f"✓ {host} reachable:\n{stdout.strip()}"
        return f"✗ {host} not responding or access denied:\n{stderr.strip()}"
    except subprocess.TimeoutExpired:
        return f"✗ {host} — TIMEOUT (12s)"
    except Exception as e:
        return f"✗ {host} — ERROR: {e}"


def tool_ssh_check_all(_args: dict) -> str:
    hosts = _parse_ssh_hosts()
    results = []
    for alias in sorted(hosts.keys()):
        try:
            rc, stdout, _ = _ssh(alias, "hostname", timeout=8)
            hostname = stdout.strip()
            if rc == 0:
                results.append(f"  ✓ {alias:<30} → {hostname}")
            else:
                results.append(f"  ✗ {alias:<30} (access denied)")
        except subprocess.TimeoutExpired:
            results.append(f"  ✗ {alias:<30} (timeout)")
        except Exception as e:
            results.append(f"  ✗ {alias:<30} ({e})")
    ok = sum(1 for r in results if "✓" in r)
    return f"{ok}/{len(hosts)} hosts reachable:\n\n" + "\n".join(results)


# ─────────────────────────────────────────
# nmap (runs locally)
# ─────────────────────────────────────────

def _nmap(args: list, timeout: int = 60) -> str:
    try:
        result = subprocess.run(
            ["nmap"] + args,
            capture_output=True, text=True, timeout=timeout
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        if result.returncode != 0 and not out:
            return f"ERROR nmap (rc={result.returncode}): {err}"
        return out
    except subprocess.TimeoutExpired:
        return f"TIMEOUT ({timeout}s) — scan took too long."
    except FileNotFoundError:
        return "ERROR: nmap is not installed on this system."
    except Exception as e:
        return f"ERROR: {e}"


def tool_nmap_discover(args: dict) -> str:
    """Ping scan: detect which hosts are alive in a network/subnet. Does not scan ports."""
    network = args["network"]
    timeout = args.get("timeout", 30)
    result = _nmap(["-sn", "-T4", "--reason", network], timeout=timeout)
    lines = result.splitlines()
    active = [l for l in lines if "Nmap scan report" in l or "Host is up" in l or "MAC Address" in l]
    summary_line = next((l for l in lines if "Nmap done" in l), "")
    if active:
        return "\n".join(active) + (f"\n\n{summary_line}" if summary_line else "")
    return result


def tool_nmap_scan(args: dict) -> str:
    """Port scan on one or more hosts/IPs."""
    target = args["target"]
    ports = args.get("ports", "")
    flags = args.get("flags", "")
    only_open = args.get("only_open", True)
    timeout = args.get("timeout", 60)

    cmd = ["-sT", "-T4"]
    if only_open:
        cmd += ["--open"]
    if ports == "-":
        cmd += ["-p-"]
    elif ports:
        cmd += ["-p", ports]
    if flags:
        cmd += flags.split()
    cmd.append(target)

    return _nmap(cmd, timeout=timeout)


def tool_nmap_audit(args: dict) -> str:
    """Full host audit: service versions + default NSE scripts."""
    host = args["host"]
    ports = args.get("ports", "")
    timeout = args.get("timeout", 120)

    cmd = ["-sT", "-sV", "-sC", "--open", "-T4"]
    if ports:
        cmd += ["-p", ports]
    cmd.append(host)

    return _nmap(cmd, timeout=timeout)


TOOLS = {
    "ssh_list_hosts": {
        "fn": tool_ssh_list_hosts,
        "description": "List all hosts available in ~/.ssh/config with their IP and user.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "title": "ssh_list_hosts",
        },
    },
    "ssh_run": {
        "fn": tool_ssh_run,
        "description": (
            "Run a command on a remote host via SSH. "
            "Uses aliases from ~/.ssh/config. "
            "If a file write is detected, automatically creates a backup before executing."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "host":    {"type": "string", "description": "SSH host alias"},
                "command": {"type": "string", "description": "Command to execute"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default 30)"},
            },
            "required": ["host", "command"],
            "title": "ssh_run",
        },
    },
    "ssh_read_file": {
        "fn": tool_ssh_read_file,
        "description": "Read the contents of a file on a remote host. Equivalent to: ssh host 'cat path'",
        "inputSchema": {
            "type": "object",
            "properties": {
                "host": {"type": "string"},
                "path": {"type": "string"},
            },
            "required": ["host", "path"],
            "title": "ssh_read_file",
        },
    },
    "ssh_write_file": {
        "fn": tool_ssh_write_file,
        "description": (
            "Write content to a file on a remote host. "
            "With backup=True (default) creates file.harper.YYYY-MM-DD before overwriting."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "host":    {"type": "string"},
                "path":    {"type": "string"},
                "content": {"type": "string"},
                "backup":  {"type": "boolean", "description": "Create backup first (default true)"},
            },
            "required": ["host", "path", "content"],
            "title": "ssh_write_file",
        },
    },
    "ssh_check": {
        "fn": tool_ssh_check,
        "description": "Check if a host is reachable via SSH. Returns hostname, uptime and remote user.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "host": {"type": "string"},
            },
            "required": ["host"],
            "title": "ssh_check",
        },
    },
    "ssh_check_all": {
        "fn": tool_ssh_check_all,
        "description": "Check SSH connectivity for all hosts in ~/.ssh/config.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "title": "ssh_check_all",
        },
    },
    "nmap_discover": {
        "fn": tool_nmap_discover,
        "description": (
            "Ping scan: detect which hosts are alive in a network or subnet. "
            "Does not scan ports — only answers 'who is up?'. "
            "Example networks: '192.168.1.0/24', '10.0.0.0/8'."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "network": {"type": "string", "description": "Network in CIDR, range or IP (e.g. 192.168.1.0/24)"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default 30)"},
            },
            "required": ["network"],
            "title": "nmap_discover",
        },
    },
    "nmap_scan": {
        "fn": tool_nmap_scan,
        "description": (
            "Scan ports on one or more hosts. "
            "By default scans top 1000 most common ports and shows only open ones. "
            "Use ports='-' for all ports, ports='22,80,443' for specific ports. "
            "Use flags='-sV' to detect service versions."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target":    {"type": "string", "description": "IP, hostname, CIDR or range"},
                "ports":     {"type": "string", "description": "Ports: '22,80,443' | '-' (all) | '' (top 1000 default)"},
                "flags":     {"type": "string", "description": "Extra nmap flags, e.g. '-sV' for versions, '-sU' for UDP"},
                "only_open": {"type": "boolean", "description": "Show only open ports (default true)"},
                "timeout":   {"type": "integer", "description": "Timeout in seconds (default 60)"},
            },
            "required": ["target"],
            "title": "nmap_scan",
        },
    },
    "nmap_audit": {
        "fn": tool_nmap_audit,
        "description": (
            "Full host audit: service versions + default NSE scripts. "
            "More thorough than nmap_scan — takes longer but gives detailed info "
            "(banners, auth, HTTP titles, etc.)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "host":    {"type": "string", "description": "Host to audit (SSH alias or IP)"},
                "ports":   {"type": "string", "description": "Optional: limit to specific ports (e.g. '22,80,443')"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default 120)"},
            },
            "required": ["host"],
            "title": "nmap_audit",
        },
    },
}

# ─────────────────────────────────────────
# MCP stdio loop
# ─────────────────────────────────────────

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
                "serverInfo": {"name": "harper-ssh", "version": "1.0"},
            },
        })

    elif method == "notifications/initialized":
        pass

    elif method == "tools/list":
        tools_list = [
            {
                "name": name,
                "description": spec["description"],
                "inputSchema": spec["inputSchema"],
            }
            for name, spec in TOOLS.items()
        ]
        _send({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": tools_list}})

    elif method == "tools/call":
        params = msg.get("params", {})
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        if tool_name not in TOOLS:
            _send({
                "jsonrpc": "2.0", "id": msg_id,
                "error": {"code": -32601, "message": f"Tool not found: {tool_name}"},
            })
            return
        try:
            result_text = TOOLS[tool_name]["fn"](arguments)
        except Exception as e:
            result_text = f"Internal ERROR: {e}"
        _send({
            "jsonrpc": "2.0", "id": msg_id,
            "result": {"content": [{"type": "text", "text": result_text}]},
        })

    elif msg_id is not None:
        _send({
            "jsonrpc": "2.0", "id": msg_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        })


def main():
    for raw_line in sys.stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            msg = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        _handle(msg)


if __name__ == "__main__":
    main()
