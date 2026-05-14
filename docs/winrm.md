# MCP WinRM — Documentación

Servidor MCP para administrar máquinas Windows de forma remota via WinRM (Windows Remote Management) directamente desde Claude Code.

## Instalación

```bash
pip install pywinrm urllib3
```

## Configurar WinRM en el lado Windows

Ejecuta esto como **Administrador** en la máquina Windows a administrar:

### Opción A — HTTP (solo red local de confianza)

```powershell
Enable-PSRemoting -Force
winrm set winrm/config/client/auth '@{Basic="true"}'
winrm set winrm/config/service/auth '@{Basic="true"}'
winrm set winrm/config/service '@{AllowUnencrypted="true"}'
```

### Opción B — HTTPS (recomendada)

```powershell
# Crear certificado autofirmado
$cert = New-SelfSignedCertificate `
    -DnsName $env:COMPUTERNAME `
    -CertStoreLocation "Cert:\LocalMachine\My" `
    -NotAfter (Get-Date).AddYears(5)

# Crear listener HTTPS en puerto 5986
New-Item -Path WSMan:\Localhost\Listener `
    -Transport HTTPS `
    -Address * `
    -CertificateThumbPrint $cert.Thumbprint `
    -Force

# Abrir puerto en firewall
New-NetFirewallRule `
    -DisplayName "WinRM HTTPS" `
    -Direction Inbound `
    -Protocol TCP `
    -LocalPort 5986 `
    -Action Allow

# Habilitar autenticación básica
winrm set winrm/config/service/auth '@{Basic="true"}'

Write-Host "Thumbprint: $($cert.Thumbprint)"
Write-Host "Endpoint: https://$env:COMPUTERNAME:5986/wsman"
```

---

## Configurar el servidor MCP

### Fichero de credenciales

Crea `~/.claude/winrm_hosts.json` (copia de `winrm_hosts.example.json`):

```bash
cp winrm_hosts.example.json ~/.claude/winrm_hosts.json
chmod 600 ~/.claude/winrm_hosts.json
```

Edita el fichero con tus hosts:

```json
{
  "_note": "Fichero local — NO añadir al repo git. chmod 600",
  "hosts": {
    "mi-pc": {
      "endpoint": "https://192.168.1.100:5986/wsman",
      "username": "administrador",
      "password": "tu-contraseña",
      "transport": "basic",
      "server_cert_validation": "ignore",
      "message_encryption": "never"
    },
    "servidor-windows": {
      "endpoint": "https://10.0.0.50:5986/wsman",
      "username": "admin",
      "password": "otra-contraseña",
      "transport": "basic",
      "server_cert_validation": "ignore",
      "message_encryption": "never"
    }
  }
}
```

### Añadir a Claude Code (`~/.claude.json`)

```json
{
  "mcpServers": {
    "harper-winrm": {
      "type": "stdio",
      "command": "python3",
      "args": ["/ruta/a/harper-mcps/mcp_winrm_server.py"],
      "env": {
        "WINRM_HOSTS_CONFIG": "/home/tuusuario/.claude/winrm_hosts.json"
      }
    }
  }
}
```

---

## Backup automático

Al igual que el MCP SSH, el servidor WinRM hace **backup automático** antes de sobreescribir cualquier fichero. El backup se crea en la misma ruta con el sufijo `.harper.YYYY-MM-DD`.

---

## Herramientas

### `winrm_list_hosts`

Lista los hosts configurados en `winrm_hosts.json` con su endpoint y si las credenciales están configuradas.

No requiere parámetros.

---

### `winrm_run_ps`

Ejecuta un script PowerShell en el host Windows.

**Parámetros:**
| Parámetro | Tipo | Por defecto | Descripción |
|-----------|------|-------------|-------------|
| `host` | string | obligatorio | Alias del host en `winrm_hosts.json` |
| `script` | string | obligatorio | Script PowerShell a ejecutar |
| `timeout` | integer | 30 | Timeout en segundos (usa >300 para Windows Update) |

**Ejemplos:**
```
winrm_run_ps(host="mi-pc", script="Get-ComputerInfo | Select-Object WindowsVersion, TotalPhysicalMemory")
winrm_run_ps(host="mi-pc", script="winget upgrade", timeout=60)
winrm_run_ps(host="mi-pc", script="Get-Service | Where Status -eq Running", timeout=30)
```

**Para Windows Update:**
```
winrm_run_ps(
    host="mi-pc",
    script="""
Install-Module PSWindowsUpdate -Force
Import-Module PSWindowsUpdate
Get-WindowsUpdate
""",
    timeout=300
)
```

---

### `winrm_read_file`

Lee el contenido de un fichero en el host Windows.

**Parámetros:**
| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `host` | string | Alias del host |
| `path` | string | Ruta Windows del fichero (ej: `C:\Users\user\config.txt`) |

**Ejemplo:**
```
winrm_read_file(host="mi-pc", path="C:\\Windows\\System32\\drivers\\etc\\hosts")
```

---

### `winrm_write_file`

Escribe contenido en un fichero del host Windows. Crea backup automático por defecto.

**Parámetros:**
| Parámetro | Tipo | Por defecto | Descripción |
|-----------|------|-------------|-------------|
| `host` | string | obligatorio | Alias del host |
| `path` | string | obligatorio | Ruta Windows destino |
| `content` | string | obligatorio | Contenido del fichero |
| `backup` | boolean | `true` | Crear backup antes |

---

### `winrm_install`

Instala software en el host Windows usando winget. Si el paquete no existe en winget, informa con la URL para descarga manual.

**Parámetros:**
| Parámetro | Tipo | Por defecto | Descripción |
|-----------|------|-------------|-------------|
| `host` | string | obligatorio | Alias del host |
| `package_id` | string | obligatorio | ID de winget (ej: `Mozilla.Firefox`) |
| `package_name` | string | `package_id` | Nombre descriptivo (opcional) |
| `timeout` | integer | 120 | Timeout en segundos |

**Ejemplos:**
```
winrm_install(host="mi-pc", package_id="Mozilla.Firefox")
winrm_install(host="mi-pc", package_id="VideoLAN.VLC", package_name="VLC Media Player")
winrm_install(host="mi-pc", package_id="7zip.7zip")
```

Para buscar IDs de paquetes: [winget.run](https://winget.run)

---

### `winrm_check`

Comprueba conectividad WinRM. Devuelve nombre del equipo, SO y hora actual.

**Parámetros:**
| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `host` | string | Alias del host |

---

## Casos de uso habituales

### Ver actualizaciones pendientes

```powershell
# Script para winrm_run_ps:
winget upgrade
```

### Instalar módulo PSWindowsUpdate y ver actualizaciones

```powershell
if (-not (Get-Module -ListAvailable PSWindowsUpdate)) {
    Install-Module PSWindowsUpdate -Force -SkipPublisherCheck
}
Import-Module PSWindowsUpdate
Get-WindowsUpdate
```

### Información del sistema

```powershell
Get-ComputerInfo | Select-Object `
    WindowsVersion, WindowsBuildLabEx, `
    CsName, CsNumberOfLogicalProcessors, `
    OsTotalVisibleMemorySize
```

### Listar procesos que más CPU usan

```powershell
Get-Process | Sort-Object CPU -Descending | Select-Object -First 10 Name, CPU, WorkingSet
```

---

## Solución de problemas

### Error `WinRMTransportError` o `Connection refused`

1. Verifica que WinRM está activo en el host Windows: `winrm enumerate winrm/config/listener`
2. Comprueba el puerto en el firewall: `Test-NetConnection -ComputerName IP -Port 5986`
3. Verifica el endpoint en `winrm_hosts.json` (HTTP usa 5985, HTTPS usa 5986)

### Error `AuthenticationError`

1. Verifica usuario y contraseña en `winrm_hosts.json`
2. Asegúrate de que la autenticación básica está habilitada:
   ```powershell
   winrm get winrm/config/service/auth
   # Basic debe ser True
   ```

### Timeout en operaciones largas

Aumenta el timeout: `timeout=300` o más. Las instalaciones con winget y Windows Update pueden tardar varios minutos.
