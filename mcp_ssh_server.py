#!/usr/bin/env python3
"""
Harper MCP — Servidor MCP para SSH a la infraestructura janet.int y ZJanet.
Usa ~/.ssh/config para resolver hosts y claves — sin contraseñas almacenadas.

Implementación MCP sobre stdio sin FastMCP (arranque <20ms vs ~760ms con FastMCP).
"""
import json
import logging
import os
import re
import shlex
import signal
import subprocess
import sys
from datetime import date
from pathlib import Path

logging.basicConfig(
    filename="/tmp/harper-ssh-mcp.log",
    level=logging.ERROR,
    format="%(asctime)s %(levelname)s %(message)s",
)

SSH_CONFIG = Path.home() / ".ssh" / "config"
SSH_OPTS = [
    "-o", "StrictHostKeyChecking=accept-new",
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=10",
]

IGNORE_PATHS = {"/dev/null", "/dev/stdin", "/dev/stdout", "/dev/stderr"}

WRITE_PATTERNS = [
    r'(?<![<2])>\s*["\']?(/[^\s"\';|&]+)',     # > /ruta (excluye 2>)
    r'\btee\s+["\']?(/[^\s"\';|&]+)',            # tee /ruta
    r'\bsed\s+-i\S*\s+\S+\s+(/[^\s"\';|&]+)',   # sed -i ... fichero
    r'\bcp\s+\S+\s+(/[^\s"\';|&]+)',             # cp origen /destino
]

# ─────────────────────────────────────────
# Lógica SSH
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
            return "[backup] fichero nuevo, sin backup necesario"
        else:
            return f"[backup] AVISO: sin permisos para backup de {host}:{path} — requiere root"
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


MAX_TIMEOUT = 60  # tope duro — evita esperas tan largas que el cliente MCP dé la sesión por muerta


def _ssh(host: str, command: str, timeout: int = 30):
    timeout = min(timeout, MAX_TIMEOUT)
    proc = subprocess.Popen(
        ["ssh"] + SSH_OPTS + [host, command],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        start_new_session=True,  # grupo de proceso propio, para poder matarlo entero si se cuelga
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        return proc.returncode, stdout, stderr
    except subprocess.TimeoutExpired:
        logging.error(
            f"TIMEOUT tras {timeout}s — host={host!r} command={command[:200]!r} — matando grupo de proceso"
        )
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logging.error(f"proceso {proc.pid} (host={host!r}) no murió tras SIGKILL a su grupo")
        raise


def _fmt(rc: int, stdout: str, stderr: str) -> str:
    out = stdout.rstrip()
    err = stderr.rstrip()
    if rc == 0:
        return out if out else "(sin salida)"
    return f"ERROR (rc={rc})\n{err or out or '(sin salida)'}"


# ─────────────────────────────────────────
# Implementación de tools
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
    return f"{len(hosts)} hosts disponibles:\n\n" + "\n".join(lines)


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
        return f"TIMEOUT ({timeout}s) — host {host} no responde o comando muy lento."
    except Exception as e:
        return f"ERROR SSH: {e}"


def tool_ssh_read_file(args: dict) -> str:
    host = args["host"]
    path = args["path"]
    try:
        rc, stdout, stderr = _ssh(host, f"cat {shlex.quote(path)}")
        if rc != 0:
            return f"No se pudo leer {path} en {host}: {stderr.strip()}"
        return f"# {host}:{path}\n\n{stdout}"
    except subprocess.TimeoutExpired:
        return f"TIMEOUT — {host} no responde."
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
            steps.append(f"Escrito: {path} ({len(content)} bytes)")
        else:
            steps.append(f"ERROR escribiendo: {stderr.strip() or stdout.strip()}")
        return "\n".join(steps)
    except subprocess.TimeoutExpired:
        return f"TIMEOUT — {host} no responde."
    except Exception as e:
        return f"ERROR: {e}"


def tool_ssh_check(args: dict) -> str:
    host = args["host"]
    try:
        rc, stdout, stderr = _ssh(host, "echo OK && hostname && uptime", timeout=12)
        if rc == 0:
            return f"✓ {host} accesible:\n{stdout.strip()}"
        return f"✗ {host} no responde o acceso denegado:\n{stderr.strip()}"
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
                results.append(f"  ✗ {alias:<30} (acceso denegado)")
        except subprocess.TimeoutExpired:
            results.append(f"  ✗ {alias:<30} (timeout)")
        except Exception as e:
            results.append(f"  ✗ {alias:<30} ({e})")
    ok = sum(1 for r in results if "✓" in r)
    return f"{ok}/{len(hosts)} hosts accesibles:\n\n" + "\n".join(results)


# ─────────────────────────────────────────
# Lógica nmap (local)
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
        return f"TIMEOUT ({timeout}s) — el escaneo tardó demasiado."
    except FileNotFoundError:
        return "ERROR: nmap no está instalado en este sistema."
    except Exception as e:
        return f"ERROR: {e}"


def tool_nmap_discover(args: dict) -> str:
    """Ping scan: detecta qué hosts están activos en una red/subred. No escanea puertos."""
    network = args["network"]
    timeout = args.get("timeout", 30)
    # -sn: solo ping, no puertos | -T4: agresivo (LAN) | --reason: mostrar método
    result = _nmap(["-sn", "-T4", "--reason", network], timeout=timeout)
    # Extraer resumen de hosts activos
    lines = result.splitlines()
    active = [l for l in lines if "Nmap scan report" in l or "Host is up" in l or "MAC Address" in l]
    summary_line = next((l for l in lines if "Nmap done" in l), "")
    if active:
        return "\n".join(active) + (f"\n\n{summary_line}" if summary_line else "")
    return result


def tool_nmap_scan(args: dict) -> str:
    """Escaneo de puertos en uno o varios hosts/IPs."""
    target = args["target"]
    ports = args.get("ports", "")       # ej: "22,80,443" o "-" para todos o vacío (top 1000)
    flags = args.get("flags", "")       # flags extra: "-sV", "-sU", etc.
    only_open = args.get("only_open", True)
    timeout = args.get("timeout", 60)

    cmd = ["-sT", "-T4"]                # TCP connect, no requiere root
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
    """Auditoría completa de un host: versiones de servicios + scripts NSE por defecto."""
    host = args["host"]
    ports = args.get("ports", "")       # opcional: limitar a puertos concretos
    timeout = args.get("timeout", 120)

    # -sT: TCP connect (sin root) | -sV: versiones | -sC: scripts default | --open: solo abiertos
    cmd = ["-sT", "-sV", "-sC", "--open", "-T4"]
    if ports:
        cmd += ["-p", ports]
    cmd.append(host)

    return _nmap(cmd, timeout=timeout)


TOOLS = {
    "ssh_list_hosts": {
        "fn": tool_ssh_list_hosts,
        "description": "Lista todos los hosts disponibles en ~/.ssh/config con su IP y usuario.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "title": "ssh_list_hosts",
        },
    },
    "ssh_run": {
        "fn": tool_ssh_run,
        "description": (
            "Ejecuta un comando en un host remoto vía SSH. "
            "Usa los alias de ~/.ssh/config — ej: 'r2d2.janet.int', 'zvision', 'zhomer'. "
            "Si detecta escritura de fichero, hace backup automático antes de ejecutar."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "host":    {"type": "string", "description": "Alias SSH del host"},
                "command": {"type": "string", "description": "Comando a ejecutar"},
                "timeout": {"type": "integer", "description": "Timeout en segundos (default 30)"},
            },
            "required": ["host", "command"],
            "title": "ssh_run",
        },
    },
    "ssh_read_file": {
        "fn": tool_ssh_read_file,
        "description": "Lee el contenido de un fichero en un host remoto. Equivale a: ssh host 'cat path'",
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
            "Escribe contenido en un fichero de un host remoto. "
            "Con backup=True (por defecto) hace cp fichero.harper.YYYY-MM-DD antes de sobreescribir."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "host":    {"type": "string"},
                "path":    {"type": "string"},
                "content": {"type": "string"},
                "backup":  {"type": "boolean", "description": "Hacer backup antes (default true)"},
            },
            "required": ["host", "path", "content"],
            "title": "ssh_write_file",
        },
    },
    "ssh_check": {
        "fn": tool_ssh_check,
        "description": "Comprueba si un host está accesible vía SSH. Devuelve hostname, uptime y usuario remoto.",
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
        "description": "Comprueba conectividad SSH en todos los hosts de ~/.ssh/config.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "title": "ssh_check_all",
        },
    },
    "nmap_discover": {
        "fn": tool_nmap_discover,
        "description": (
            "Ping scan: detecta qué hosts están activos en una red o subred. "
            "No escanea puertos — solo responde '¿quién está vivo?'. "
            "Ejemplos de network: '172.16.0.0/27', '172.16.1.0/27', '10.0.34.0/27', '172.16.3.0/27'."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "network": {"type": "string", "description": "Red en CIDR, rango o IP (ej: 172.16.1.0/27)"},
                "timeout": {"type": "integer", "description": "Timeout en segundos (default 30)"},
            },
            "required": ["network"],
            "title": "nmap_discover",
        },
    },
    "nmap_scan": {
        "fn": tool_nmap_scan,
        "description": (
            "Escanea puertos en uno o varios hosts. "
            "Por defecto escanea los 1000 puertos más comunes y muestra solo los abiertos. "
            "Usar ports='-' para todos los puertos, ports='22,80,443' para puertos concretos. "
            "Usar flags='-sV' para detectar versiones de servicios."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target":    {"type": "string", "description": "IP, hostname, CIDR o rango (ej: r2d2.janet.int, 172.16.1.0/27)"},
                "ports":     {"type": "string", "description": "Puertos: '22,80,443' | '-' (todos) | '' (top 1000 default)"},
                "flags":     {"type": "string", "description": "Flags nmap extra, ej: '-sV' para versiones, '-sU' para UDP"},
                "only_open": {"type": "boolean", "description": "Mostrar solo puertos abiertos (default true)"},
                "timeout":   {"type": "integer", "description": "Timeout en segundos (default 60)"},
            },
            "required": ["target"],
            "title": "nmap_scan",
        },
    },
    "nmap_audit": {
        "fn": tool_nmap_audit,
        "description": (
            "Auditoría completa de un host: versiones de servicios + scripts NSE por defecto. "
            "Más profundo que nmap_scan — tarda más pero da info detallada (banner, auth, título HTTP, etc.)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "host":    {"type": "string", "description": "Host a auditar (alias SSH o IP)"},
                "ports":   {"type": "string", "description": "Opcional: limitar a puertos concretos (ej: '22,80,443')"},
                "timeout": {"type": "integer", "description": "Timeout en segundos (default 120)"},
            },
            "required": ["host"],
            "title": "nmap_audit",
        },
    },
}

# ─────────────────────────────────────────
# Loop MCP sobre stdio
# ─────────────────────────────────────────

def _send(obj: dict):
    try:
        sys.stdout.write(json.dumps(obj) + "\n")
        sys.stdout.flush()
    except BrokenPipeError:
        sys.exit(0)
    except Exception as e:
        logging.error(f"_send error: {e}")
        sys.exit(1)


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
        pass  # notificación, sin respuesta

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
            result_text = f"ERROR interno: {e}"
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
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    for raw_line in sys.stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            msg = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        try:
            _handle(msg)
        except Exception as e:
            logging.error(f"_handle error: {e}")


if __name__ == "__main__":
    main()
