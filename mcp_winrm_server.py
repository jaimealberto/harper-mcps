#!/usr/bin/env python3
"""
MCP server for remote Windows administration via WinRM.

Credentials stored in ~/.claude/winrm_hosts.json (outside the repo, chmod 600).
MCP over stdio without FastMCP (startup <20ms).

Configure the path to the credentials file:
  export WINRM_HOSTS_CONFIG=/path/to/winrm_hosts.json  (default: ~/.claude/winrm_hosts.json)

Tools:
  winrm_list_hosts  — list configured hosts
  winrm_run_ps      — run PowerShell script
  winrm_read_file   — read a Windows file
  winrm_write_file  — write a Windows file with auto-backup
  winrm_install     — install software via winget
  winrm_check       — connectivity test
"""
import json
import os
import re
import sys
import warnings
from datetime import date
from pathlib import Path

warnings.filterwarnings("ignore")

import winrm
import urllib3
urllib3.disable_warnings()

CONFIG_PATH = Path(os.environ.get(
    "WINRM_HOSTS_CONFIG",
    str(Path.home() / ".claude" / "winrm_hosts.json")
))

DEFAULT_CONFIG = {
    "_note": "Local file — DO NOT add to git repo. chmod 600 winrm_hosts.json",
    "hosts": {
        "my-windows-host": {
            "endpoint": "https://192.168.1.100:5986/wsman",
            "username": "administrator",
            "password": "CHANGE_ME",
            "transport": "basic",
            "server_cert_validation": "ignore",
            "message_encryption": "never"
        }
    }
}

# ─────────────────────────────────────────
# Config and connection
# ─────────────────────────────────────────

def _load_config() -> dict:
    if not CONFIG_PATH.exists():
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2, ensure_ascii=False))
        CONFIG_PATH.chmod(0o600)
    return json.loads(CONFIG_PATH.read_text())


def _get_session(host_alias: str, timeout: int = 30) -> winrm.Session:
    cfg = _load_config()
    hosts = cfg.get("hosts", {})
    if host_alias not in hosts:
        available = ", ".join(hosts.keys()) or "(none)"
        raise ValueError(f"Host '{host_alias}' not found. Available: {available}")
    h = hosts[host_alias]
    if h.get("password") == "CHANGE_ME":
        raise ValueError(f"Credentials not configured for '{host_alias}'. Edit {CONFIG_PATH}")
    return winrm.Session(
        h["endpoint"],
        auth=(h["username"], h["password"]),
        transport=h.get("transport", "basic"),
        server_cert_validation=h.get("server_cert_validation", "ignore"),
        message_encryption=h.get("message_encryption", "never"),
        operation_timeout_sec=timeout,
        read_timeout_sec=timeout + 10,
    )


# ─────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────

def _decode(b: bytes) -> str:
    for enc in ("utf-8", "cp850", "latin-1"):
        try:
            return b.decode(enc)
        except (UnicodeDecodeError, AttributeError):
            continue
    return b.decode("utf-8", errors="replace")


def _strip_clixml(text: str) -> str:
    """Extract readable text from PowerShell's CLIXML stderr wrapper."""
    if "<Objs" not in text:
        return text.strip()
    parts = re.findall(r'<S[^>]*>([^<]*)</S>', text)
    cleaned = []
    for p in parts:
        p = p.replace("_x000D__x000A_", "\n").replace("_x000A_", "\n")
        p = re.sub(r'_x[0-9A-Fa-f]{4}_', '', p).strip()
        if p:
            cleaned.append(p)
    return "\n".join(cleaned).strip()


def _run_ps(host: str, script: str, timeout: int = 30) -> dict:
    conn = _get_session(host, timeout)
    r = conn.run_ps(script)
    stdout = _decode(r.std_out).strip()
    stderr = _strip_clixml(_decode(r.std_err))
    return {"stdout": stdout, "stderr": stderr, "rc": r.status_code}


def _fmt_result(res: dict) -> str:
    out = res["stdout"]
    err = res["stderr"]
    rc = res["rc"]
    parts = []
    if out:
        parts.append(out)
    if err and rc != 0:
        parts.append(f"[stderr] {err}")
    elif err and "warning" in err.lower():
        parts.append(f"[warning] {err}")
    if not parts:
        parts.append(f"(no output — rc={rc})")
    return "\n".join(parts)


# ─────────────────────────────────────────
# Tool implementations
# ─────────────────────────────────────────

def tool_winrm_list_hosts(_args: dict) -> str:
    cfg = _load_config()
    hosts = cfg.get("hosts", {})
    if not hosts:
        return f"No hosts configured. Edit {CONFIG_PATH}"
    lines = []
    for alias, h in hosts.items():
        endpoint = h.get("endpoint", "?")
        user = h.get("username", "?")
        configured = "✓" if h.get("password", "CHANGE_ME") != "CHANGE_ME" else "✗ (no credentials)"
        lines.append(f"  {alias:<20} {user}@{endpoint}  {configured}")
    return f"{len(hosts)} Windows hosts configured:\n\n" + "\n".join(lines)


def tool_winrm_run_ps(args: dict) -> str:
    host = args["host"]
    script = args["script"]
    timeout = int(args.get("timeout", 30))
    try:
        res = _run_ps(host, script, timeout)
        return _fmt_result(res)
    except Exception as e:
        return f"ERROR: {e}"


def tool_winrm_read_file(args: dict) -> str:
    host = args["host"]
    path = args["path"]
    try:
        res = _run_ps(host, f'Get-Content -Path "{path}" -Raw -ErrorAction Stop', timeout=20)
        if res["rc"] != 0:
            return f"ERROR reading {path}: {res['stderr'] or res['stdout']}"
        return f"# {host}:{path}\n\n{res['stdout']}"
    except Exception as e:
        return f"ERROR: {e}"


def tool_winrm_write_file(args: dict) -> str:
    host = args["host"]
    path = args["path"]
    content = args["content"]
    backup = args.get("backup", True)
    steps = []
    try:
        if backup:
            today = date.today().isoformat()
            backup_path = path.replace("\\", "\\\\") + f".harper.{today}"
            path_escaped = path.replace("\\", "\\\\")
            bk_script = f'''
if (Test-Path "{path_escaped}") {{
    Copy-Item "{path_escaped}" "{backup_path}"
    Write-Host "BACKUP_OK:{backup_path}"
}} else {{
    Write-Host "BACKUP_NEW"
}}
'''
            bk_res = _run_ps(host, bk_script, timeout=15)
            if "BACKUP_OK" in bk_res["stdout"]:
                steps.append(f"[backup] {host}:{backup_path}")
            else:
                steps.append("[backup] new file, no backup needed")

        import base64
        b64 = base64.b64encode(content.encode("utf-8")).decode()
        path_escaped = path.replace("\\", "\\\\")
        write_script = f'''
$bytes = [Convert]::FromBase64String("{b64}")
[System.IO.File]::WriteAllBytes("{path_escaped}", $bytes)
Write-Host "WRITTEN:{path_escaped}"
'''
        wr_res = _run_ps(host, write_script, timeout=20)
        if "WRITTEN" in wr_res["stdout"]:
            steps.append(f"Written: {path} ({len(content)} bytes)")
        else:
            steps.append(f"ERROR: {wr_res['stderr'] or wr_res['stdout']}")
        return "\n".join(steps)
    except Exception as e:
        return f"ERROR: {e}"


def tool_winrm_install(args: dict) -> str:
    """
    Install software on the Windows host.
    Strategy: winget first (preferred). If it fails, reports for manual download.
    """
    host = args["host"]
    package_id = args["package_id"]
    package_name = args.get("package_name", package_id)
    timeout = int(args.get("timeout", 120))

    script = f'''
Write-Host "=== Installing: {package_name} ==="
Write-Host "Trying via winget (id: {package_id})..."
$wg = winget install --id "{package_id}" --accept-source-agreements --accept-package-agreements --silent 2>&1
$wg | ForEach-Object {{ Write-Host $_ }}
$rc = $LASTEXITCODE

if ($rc -eq 0) {{
    Write-Host "RESULT: Successfully installed via winget"
}} elseif ($rc -eq -1978335189) {{
    Write-Host "RESULT: Already installed (winget confirms)"
}} elseif ($rc -eq -1978335212) {{
    Write-Host "RESULT: Not found in winget — search at https://winget.run or download manually"
}} else {{
    Write-Host "RESULT: winget rc=$rc — if it fails, find installer at https://winget.run/pkg/$("{package_id}".Replace('.','/'))"
}}
'''
    try:
        res = _run_ps(host, script, timeout)
        return _fmt_result(res)
    except Exception as e:
        return f"ERROR: {e}"


def tool_winrm_check(args: dict) -> str:
    host = args["host"]
    try:
        res = _run_ps(host, '$env:COMPUTERNAME + " — " + $env:OS + " — " + (Get-Date -Format "HH:mm")', timeout=12)
        if res["rc"] == 0 and res["stdout"]:
            return f"✓ {host} reachable: {res['stdout']}"
        return f"✗ {host}: {res['stderr'] or '(no response)'}"
    except Exception as e:
        return f"✗ {host} — ERROR: {e}"


# ─────────────────────────────────────────
# Tool registry
# ─────────────────────────────────────────

TOOLS = {
    "winrm_list_hosts": {
        "fn": tool_winrm_list_hosts,
        "description": "List configured Windows hosts from winrm_hosts.json with their endpoint and credential status.",
        "inputSchema": {"type": "object", "properties": {}, "title": "winrm_list_hosts"},
    },
    "winrm_run_ps": {
        "fn": tool_winrm_run_ps,
        "description": (
            "Run a PowerShell script on a Windows host via WinRM. "
            "For long operations (Windows Update, installations) use timeout > 300."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "host":    {"type": "string", "description": "Host alias (from winrm_hosts.json)"},
                "script":  {"type": "string", "description": "PowerShell script to execute"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default 30, max 600)"},
            },
            "required": ["host", "script"],
            "title": "winrm_run_ps",
        },
    },
    "winrm_read_file": {
        "fn": tool_winrm_read_file,
        "description": "Read the contents of a file on the Windows host. Path in Windows format (e.g. 'C:\\\\Users\\\\user\\\\doc.txt').",
        "inputSchema": {
            "type": "object",
            "properties": {
                "host": {"type": "string"},
                "path": {"type": "string", "description": "Windows path to the file"},
            },
            "required": ["host", "path"],
            "title": "winrm_read_file",
        },
    },
    "winrm_write_file": {
        "fn": tool_winrm_write_file,
        "description": (
            "Write content to a file on the Windows host. "
            "With backup=true (default) creates file.harper.YYYY-MM-DD before overwriting."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "host":    {"type": "string"},
                "path":    {"type": "string", "description": "Windows destination path"},
                "content": {"type": "string", "description": "File content"},
                "backup":  {"type": "boolean", "description": "Create backup first (default true)"},
            },
            "required": ["host", "path", "content"],
            "title": "winrm_write_file",
        },
    },
    "winrm_install": {
        "fn": tool_winrm_install,
        "description": (
            "Install software on the Windows host. "
            "Strategy: winget first (preferred). "
            "If the package is not in winget, reports with the URL for manual download. "
            "package_id is the winget ID (e.g. 'Mozilla.Firefox', 'VideoLAN.VLC')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "host":         {"type": "string"},
                "package_id":   {"type": "string", "description": "winget ID (e.g. 'Mozilla.Firefox')"},
                "package_name": {"type": "string", "description": "Descriptive name (optional)"},
                "timeout":      {"type": "integer", "description": "Timeout in seconds (default 120)"},
            },
            "required": ["host", "package_id"],
            "title": "winrm_install",
        },
    },
    "winrm_check": {
        "fn": tool_winrm_check,
        "description": "Check WinRM connectivity with the Windows host. Returns hostname, OS and current time.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "host": {"type": "string"},
            },
            "required": ["host"],
            "title": "winrm_check",
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
                "serverInfo": {"name": "harper-winrm", "version": "1.0"},
            },
        })

    elif method == "notifications/initialized":
        pass

    elif method == "tools/list":
        _send({
            "jsonrpc": "2.0", "id": msg_id,
            "result": {
                "tools": [
                    {
                        "name": name,
                        "description": spec["description"],
                        "inputSchema": spec["inputSchema"],
                    }
                    for name, spec in TOOLS.items()
                ]
            },
        })

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
