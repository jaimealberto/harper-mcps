# MCP SSH + nmap — Documentación

Servidor MCP para ejecutar comandos en hosts remotos via SSH y realizar escaneos de red con nmap, directamente desde Claude Code.

## Instalación

```bash
# Sin dependencias Python adicionales
# Requiere ssh en PATH (habitual en cualquier Linux/macOS)
# Requiere nmap para las herramientas nmap_*:
sudo apt install nmap    # Debian/Ubuntu
brew install nmap        # macOS
```

## Configuración

El servidor lee hosts y claves de `~/.ssh/config`. No almacena contraseñas en ningún lado.

### Ejemplo `~/.ssh/config`

```
Host servidor01
    HostName 192.168.1.10
    User admin
    IdentityFile ~/.ssh/id_ed25519

Host servidor02
    HostName 192.168.1.20
    User root
    Port 22222
    IdentityFile ~/.ssh/id_rsa

Host servidor-remoto
    HostName 10.0.0.5
    User sistemas
    ProxyJump bastion.ejemplo.com
```

### Añadir a Claude Code (`~/.claude.json`)

```json
{
  "mcpServers": {
    "harper-ssh": {
      "type": "stdio",
      "command": "python3",
      "args": ["/ruta/a/harper-mcps/mcp_ssh_server.py"],
      "env": {}
    }
  }
}
```

---

## Backup automático

Cuando el servidor detecta que un comando escribe sobre un fichero remoto, **hace backup automático antes de ejecutar**. El backup se crea en la misma ruta con el sufijo `.harper.YYYY-MM-DD`.

Patrones detectados automáticamente:
- Redirección: `comando > /ruta/fichero`
- `tee /ruta/fichero`
- `sed -i ... /ruta/fichero`
- `cp origen /destino`

**Ejemplo:** Si ejecutas `echo "nuevo" > /etc/app/config.conf`, el servidor primero hace `cp /etc/app/config.conf /etc/app/config.conf.harper.2026-05-14` y luego ejecuta el comando.

---

## Herramientas SSH

### `ssh_list_hosts`

Lista todos los hosts definidos en `~/.ssh/config` con su hostname, usuario y puerto.

No requiere parámetros.

---

### `ssh_run`

Ejecuta un comando en un host remoto.

**Parámetros:**
| Parámetro | Tipo | Por defecto | Descripción |
|-----------|------|-------------|-------------|
| `host` | string | obligatorio | Alias del host en `~/.ssh/config` |
| `command` | string | obligatorio | Comando a ejecutar |
| `timeout` | integer | 30 | Timeout en segundos |

**Ejemplos:**
```
ssh_run(host="servidor01", command="df -h")
ssh_run(host="servidor01", command="systemctl status nginx")
ssh_run(host="servidor01", command="tail -100 /var/log/syslog", timeout=15)
```

---

### `ssh_read_file`

Lee el contenido de un fichero remoto (equivale a `ssh host 'cat ruta'`).

**Parámetros:**
| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `host` | string | Alias SSH |
| `path` | string | Ruta absoluta al fichero |

**Ejemplo:**
```
ssh_read_file(host="servidor01", path="/etc/nginx/nginx.conf")
```

---

### `ssh_write_file`

Escribe contenido en un fichero remoto. Hace backup automático por defecto.

**Parámetros:**
| Parámetro | Tipo | Por defecto | Descripción |
|-----------|------|-------------|-------------|
| `host` | string | obligatorio | Alias SSH |
| `path` | string | obligatorio | Ruta destino |
| `content` | string | obligatorio | Contenido a escribir |
| `backup` | boolean | `true` | Crear backup antes |

**Ejemplo:**
```
ssh_write_file(host="servidor01", path="/etc/app/config.conf", content="nueva configuración")
```

---

### `ssh_check`

Comprueba si un host es accesible via SSH. Devuelve hostname, uptime y usuario.

**Parámetros:**
| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `host` | string | Alias SSH |

---

### `ssh_check_all`

Comprueba todos los hosts de `~/.ssh/config` en paralelo. Útil para ver el estado general de la infraestructura.

No requiere parámetros.

---

## Herramientas nmap

> ℹ️ Las herramientas nmap se ejecutan en la máquina local donde corre Claude Code, no en el host remoto.

### `nmap_discover`

Ping scan para detectar qué hosts están activos en una red. **No escanea puertos.**

**Parámetros:**
| Parámetro | Tipo | Por defecto | Descripción |
|-----------|------|-------------|-------------|
| `network` | string | obligatorio | Red en CIDR, rango o IP (ej: `192.168.1.0/24`) |
| `timeout` | integer | 30 | Timeout en segundos |

**Ejemplos:**
```
nmap_discover(network="192.168.1.0/24")
nmap_discover(network="10.0.0.0/8", timeout=60)
```

---

### `nmap_scan`

Escaneo de puertos en uno o varios hosts.

**Parámetros:**
| Parámetro | Tipo | Por defecto | Descripción |
|-----------|------|-------------|-------------|
| `target` | string | obligatorio | IP, hostname, CIDR o rango |
| `ports` | string | top 1000 | `"22,80,443"` / `"-"` (todos) / `""` (top 1000) |
| `flags` | string | `""` | Flags extra de nmap |
| `only_open` | boolean | `true` | Mostrar solo puertos abiertos |
| `timeout` | integer | 60 | Timeout en segundos |

**Ejemplos:**
```
nmap_scan(target="192.168.1.10")
nmap_scan(target="192.168.1.10", ports="22,80,443,8080")
nmap_scan(target="192.168.1.0/24", flags="-sV")   # con versiones de servicios
nmap_scan(target="192.168.1.10", ports="-")        # todos los puertos
```

---

### `nmap_audit`

Auditoría completa de un host: versiones de servicios + scripts NSE por defecto. Más lento pero más informativo que `nmap_scan`.

**Parámetros:**
| Parámetro | Tipo | Por defecto | Descripción |
|-----------|------|-------------|-------------|
| `host` | string | obligatorio | Host a auditar (alias SSH o IP) |
| `ports` | string | todos | Limitar a puertos concretos |
| `timeout` | integer | 120 | Timeout en segundos |

**Ejemplo:**
```
nmap_audit(host="servidor01", ports="22,80,443")
```

---

## Notas de uso

- El servidor usa `-sT` (TCP connect) para nmap, que **no requiere privilegios root**.
- Para escaneos UDP (`-sU`) o SYN scan (`-sS`) sí se necesita root: ejecuta Claude Code como root o con sudo.
- El timeout de `ssh_run` por defecto es 30s. Para comandos lentos (compilaciones, operaciones de backup) auméntalo: `timeout=300`.
- Los alias `*` y `github.com` se excluyen automáticamente de `ssh_list_hosts` y `ssh_check_all`.
