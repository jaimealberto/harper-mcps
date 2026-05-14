# harper-mcps

Colección de servidores MCP (_Model Context Protocol_) para [Claude Code](https://claude.ai/code) que permiten gestionar infraestructura, acceder a vaults de Obsidian, administrar máquinas Windows y realizar investigación OSINT.

Diseñados para un homelab autogestionado. Todos los servidores usan transporte stdio sin FastMCP para un arranque rápido (<20ms).

## Servidores incluidos

| Servidor | Herramientas | Dependencias |
|----------|-------------|--------------|
| `mcp_obsidian_server.py` | search, read, write, list, tags, backlinks, structure | `mcp` |
| `mcp_ssh_server.py` | ssh_run, ssh_read/write_file, ssh_check, nmap_discover/scan/audit | `nmap` (sistema) |
| `mcp_winrm_server.py` | winrm_run_ps, winrm_read/write_file, winrm_install, winrm_check | `pywinrm` |
| `mcp_osint_server.py` | username, email, social, domain, whois, dns, phone, ip, breach, dossier | ver más abajo |

---

## Instalación rápida

### 1. Clonar el repositorio

```bash
git clone https://github.com/JaimeAlberto/harper-mcps.git
cd harper-mcps
```

### 2. Instalar dependencias

**MCP Obsidian:**
```bash
pip install mcp
```

**MCP SSH + nmap:**
```bash
# Sin dependencias Python — usa ssh y nmap del sistema
sudo apt install nmap        # Debian/Ubuntu
# brew install nmap          # macOS
```

**MCP WinRM:**
```bash
pip install pywinrm urllib3
```

**MCP OSINT:**
```bash
# Librerías base (obligatorias):
pip install python-whois dnspython phonenumbers

# Herramientas opcionales (para búsquedas más profundas):
pip install maigret holehe sherlock-project theHarvester
```

### 3. Configurar

Copia los ficheros de ejemplo:
```bash
cp .env.example .env
# Edita .env con tus rutas

cp winrm_hosts.example.json ~/.claude/winrm_hosts.json
chmod 600 ~/.claude/winrm_hosts.json
# Edita con tus hosts Windows y credenciales
```

### 4. Añadir a Claude Code

Añade a `~/.claude.json` bajo la clave `mcpServers` (o usa `claude mcp add`):

```json
{
  "mcpServers": {
    "harper-obsidian": {
      "type": "stdio",
      "command": "python3",
      "args": ["/ruta/a/harper-mcps/mcp_obsidian_server.py"],
      "env": {
        "OBSIDIAN_VAULT": "/home/tuusuario/Obsidian"
      }
    }
  }
}
```

Consulta `claude_settings_example.json` para ver la configuración de los cuatro servidores a la vez.

---

## Detalle de cada servidor

### MCP Obsidian (`harper-obsidian`)

Permite a Claude Code leer y escribir directamente en tu vault de [Obsidian](https://obsidian.md).

📄 [Documentación completa → docs/obsidian.md](docs/obsidian.md)

**Variables de entorno:**

| Variable | Valor por defecto | Descripción |
|----------|-------------------|-------------|
| `OBSIDIAN_VAULT` | `~/Obsidian` | Ruta al vault |

**Herramientas disponibles:**

| Herramienta | Descripción |
|-------------|-------------|
| `search_vault` | Busca texto en todas las notas con fragmento de contexto |
| `read_note` | Lee una nota por ruta relativa al vault |
| `write_note` | Escribe o sobreescribe una nota |
| `list_notes` | Lista notas de un directorio (recursivo) |
| `find_by_tag` | Encuentra notas por tag en frontmatter o cuerpo |
| `get_backlinks` | Encuentra notas que enlazan a una nota concreta |
| `vault_structure` | Estructura de carpetas con conteo de notas |

**Ejemplos de uso:**
- "Busca en mi vault notas sobre Python"
- "Lee la nota Proyectos/mi-proyecto.md"
- "Lista todas las notas con el tag #pendiente"
- "¿Qué notas enlazan a la nota weekly-review?"

---

### MCP SSH + nmap (`harper-ssh`)

Ejecuta comandos en hosts Linux/Unix remotos via SSH y escanea redes con nmap.
Lee la configuración de hosts desde `~/.ssh/config` — sin contraseñas almacenadas.

📄 [Documentación completa → docs/ssh.md](docs/ssh.md)

**Características destacadas:**
- Backup automático antes de escribir ficheros (crea `fichero.harper.YYYY-MM-DD`)
- Detecta operaciones de escritura en el comando y hace backup del fichero destino
- Ping scan, escaneo de puertos y auditoría completa de servicios con nmap

**Herramientas disponibles:**

| Herramienta | Descripción |
|-------------|-------------|
| `ssh_list_hosts` | Lista hosts del `~/.ssh/config` con IP y usuario |
| `ssh_run` | Ejecuta un comando en un host remoto |
| `ssh_read_file` | Lee el contenido de un fichero remoto |
| `ssh_write_file` | Escribe un fichero remoto (con backup automático) |
| `ssh_check` | Comprueba conectividad SSH con un host |
| `ssh_check_all` | Comprueba todos los hosts a la vez |
| `nmap_discover` | Ping scan: detecta hosts activos en una red |
| `nmap_scan` | Escaneo de puertos en uno o varios hosts |
| `nmap_audit` | Auditoría completa: versiones de servicios + scripts NSE |

**Ejemplos de uso:**
- "Lista mis hosts SSH"
- "Ejecuta `df -h` en servidor01"
- "Escanea los puertos 22,80,443 en 192.168.1.0/24"
- "¿Qué hosts están activos en mi red?"

---

### MCP WinRM (`harper-winrm`)

Administra máquinas Windows de forma remota via WinRM (Windows Remote Management).

📄 [Documentación completa → docs/winrm.md](docs/winrm.md)

**Requisitos en el lado Windows** (ejecutar como Administrador):
```powershell
Enable-PSRemoting -Force
# Para HTTPS (recomendado):
New-SelfSignedCertificate -DnsName "NOMBRE_PC" -CertStoreLocation Cert:\LocalMachine\My
winrm create winrm/config/Listener?Address=*+Transport=HTTPS @{Port="5986";CertificateThumbprint="THUMBPRINT"}
```

**Fichero de credenciales** (`~/.claude/winrm_hosts.json`, chmod 600):
```json
{
  "hosts": {
    "mi-pc": {
      "endpoint": "https://192.168.1.100:5986/wsman",
      "username": "administrador",
      "password": "tu-contraseña",
      "transport": "basic",
      "server_cert_validation": "ignore",
      "message_encryption": "never"
    }
  }
}
```

**Variables de entorno:**

| Variable | Valor por defecto | Descripción |
|----------|-------------------|-------------|
| `WINRM_HOSTS_CONFIG` | `~/.claude/winrm_hosts.json` | Ruta al fichero de credenciales |

**Herramientas disponibles:**

| Herramienta | Descripción |
|-------------|-------------|
| `winrm_list_hosts` | Lista hosts configurados y estado de credenciales |
| `winrm_run_ps` | Ejecuta un script PowerShell en el host Windows |
| `winrm_read_file` | Lee el contenido de un fichero Windows |
| `winrm_write_file` | Escribe un fichero Windows (con backup automático) |
| `winrm_install` | Instala software via winget |
| `winrm_check` | Comprueba conectividad WinRM |

**Ejemplos de uso:**
- "¿Está encendido mi-pc?"
- "Ejecuta `winget upgrade` en mi-pc y muéstrame las actualizaciones pendientes"
- "Instala Mozilla.Firefox en mi-pc via winget"
- "Lee el fichero C:\Users\usuario\AppData\Local\app\config.ini de mi-pc"

---

### MCP OSINT (`harper-osint`)

Herramientas de inteligencia de fuentes abiertas integradas en Claude Code. Envuelve maigret, holehe, sherlock, theHarvester y librerías estándar.

📄 [Documentación completa → docs/osint.md](docs/osint.md)

> ⚠️ **Aviso legal:** Usa estas herramientas solo sobre objetivos para los que tengas autorización. El uso sobre terceros sin consentimiento puede ser ilegal en tu país.

**Variables de entorno:**

| Variable | Valor por defecto | Descripción |
|----------|-------------------|-------------|
| `OSINT_VAULT` | `~/osint-reports` | Directorio donde guardar los informes |
| `THEHARVESTER_BIN` | auto-detect | Ruta al binario de theHarvester |

**Herramientas disponibles:**

| Herramienta | Qué hace | Requiere |
|-------------|---------|----------|
| `osint_status` | Comprueba herramientas instaladas | — |
| `osint_username` | Username en 3000+ sitios (Maigret) | `pip install maigret` |
| `osint_email` | Email en 120+ servicios (Holehe) | `pip install holehe` |
| `osint_social_scan` | Username en 400+ redes (Sherlock) | `pip install sherlock-project` |
| `osint_domain` | Emails/subdominios/IPs (TheHarvester) | `pip install theHarvester` |
| `osint_whois` | WHOIS de dominio o IP | `pip install python-whois` |
| `osint_dns` | DNS completo + SPF/DMARC/DKIM | `pip install dnspython` |
| `osint_phone` | País/operador/tipo de un teléfono | `pip install phonenumbers` |
| `osint_ip` | ASN/geo/abuse de una IP pública | — (usa ipinfo.io) |
| `osint_breach_check` | Email en brechas HIBP | — (API key opcional) |
| `osint_dossier` | Informe completo combinando todas las tools | según tipo de objetivo |

**Ejemplos de uso:**
- "Comprueba el estado de las herramientas OSINT instaladas"
- "Haz un WHOIS de ejemplo.com"
- "Analiza el DNS de empresa.com y dime si tiene SPF y DMARC"
- "¿Aparece usuario@ejemplo.com en alguna brecha de datos?"
- "Genera un dossier completo sobre el dominio empresa.com"

---

## Notas de seguridad

- **MCP SSH:** Sin credenciales almacenadas — usa `~/.ssh/config` y claves SSH.
- **MCP WinRM:** Credenciales en `winrm_hosts.json` fuera del repo. Mantener `chmod 600` y nunca hacer commit.
- **MCP OSINT:** Todas las herramientas hacen peticiones de red. Respeta los límites de uso y términos de servicio de cada plataforma.
- **nmap:** Algunos tipos de escaneo requieren root. Los servidores usan `-sT` (TCP connect) que no necesita privilegios.

---

## Licencia

MIT. Úsalos bajo tu propia responsabilidad. Estas herramientas realizan conexiones de red reales y pueden modificar sistemas remotos.
