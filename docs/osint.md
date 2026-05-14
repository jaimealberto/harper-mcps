# MCP OSINT — Documentación

Servidor MCP para investigación de inteligencia de fuentes abiertas (OSINT) integrado en Claude Code. Envuelve herramientas como maigret, holehe, sherlock, theHarvester y librerías Python estándar.

> ⚠️ **Aviso legal:** Usa estas herramientas exclusivamente sobre objetivos para los que tengas autorización expresa (propia infraestructura, pruebas de penetración contratadas, investigación académica, CTF). El uso sobre terceros sin consentimiento puede constituir una infracción legal en tu país.

---

## Instalación

### Dependencias base (necesarias para whois, dns, phone):

```bash
pip install python-whois dnspython phonenumbers
```

### Herramientas opcionales:

```bash
# Búsqueda de usernames en 3000+ sitios
pip install maigret

# Detección de email en 120+ plataformas
pip install holehe

# Búsqueda rápida en 400+ redes sociales
pip install sherlock-project

# Recolección de emails/subdominios/IPs de un dominio
pip install theHarvester
```

### Instalar en entorno aislado (recomendado para theHarvester)

theHarvester puede tener conflictos de dependencias con otras herramientas. Se recomienda un entorno conda o venv separado:

```bash
# Con conda:
conda create -n osint python=3.12
conda activate osint
pip install maigret holehe sherlock-project theHarvester python-whois dnspython phonenumbers

# Con venv:
python3 -m venv ~/.venv/osint
source ~/.venv/osint/bin/activate
pip install maigret holehe sherlock-project theHarvester python-whois dnspython phonenumbers
```

Si usas un entorno separado, define `THEHARVESTER_BIN`:
```bash
export THEHARVESTER_BIN=/home/usuario/.conda/envs/osint/bin/theHarvester
```

---

## Configuración

### Variables de entorno

| Variable | Por defecto | Descripción |
|----------|-------------|-------------|
| `OSINT_VAULT` | `~/osint-reports` | Directorio donde guardar informes |
| `THEHARVESTER_BIN` | auto-detect via PATH | Ruta al binario de theHarvester |

### Añadir a Claude Code (`~/.claude.json`)

```json
{
  "mcpServers": {
    "harper-osint": {
      "type": "stdio",
      "command": "/home/usuario/.conda/envs/osint/bin/python",
      "args": ["/ruta/a/harper-mcps/mcp_osint_server.py"],
      "env": {
        "OSINT_VAULT": "/home/usuario/osint-reports",
        "THEHARVESTER_BIN": "/home/usuario/.conda/envs/osint/bin/theHarvester"
      }
    }
  }
}
```

---

## Herramientas

### `osint_status`

Comprueba qué herramientas OSINT están instaladas y disponibles. Muestra el comando de instalación para las que falten.

No requiere parámetros. Úsala siempre como primer paso.

---

### `osint_username` — Maigret

Busca un username en más de 3000 sitios web. Extrae URLs de perfiles, datos personales encontrados y usernames alternativos. Guarda el informe en JSON en `OSINT_VAULT`.

**Parámetros:**
| Parámetro | Tipo | Por defecto | Descripción |
|-----------|------|-------------|-------------|
| `username` | string | obligatorio | Username a investigar |
| `limit` | integer | 500 | Número de sitios a comprobar (máx 3000) |
| `save_report` | boolean | `true` | Guardar JSON en `OSINT_VAULT` |

**Tiempo estimado:** 1-3 minutos con limit=500, hasta 10 minutos con limit=3000.

**Ejemplo:**
```
osint_username("johndoe", limit=500)
```

---

### `osint_email` — Holehe

Comprueba en qué servicios online está registrado un email en 120+ plataformas. Usa la función de recuperación de contraseña — no crea cuentas ni deja rastro en los servicios.

**Parámetros:**
| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `email` | string | Email a investigar |

**Ejemplo:**
```
osint_email("usuario@ejemplo.com")
```

---

### `osint_social_scan` — Sherlock

Búsqueda rápida de username en 400+ redes sociales. Más rápido que Maigret pero menos profundo. Ideal como primer paso de una investigación.

**Parámetros:**
| Parámetro | Tipo | Por defecto | Descripción |
|-----------|------|-------------|-------------|
| `username` | string | obligatorio | Username a buscar |
| `timeout_per_site` | integer | 10 | Timeout por sitio en segundos |

**Ejemplo:**
```
osint_social_scan("johndoe")
```

---

### `osint_domain` — TheHarvester

Recopila información pública de un dominio: emails corporativos, subdominios, IPs, nombres de empleados. Fuentes disponibles: `duckduckgo`, `yahoo`, `hackertarget`, `crtsh`, `rapiddns`, `urlscan`.

**Parámetros:**
| Parámetro | Tipo | Por defecto | Descripción |
|-----------|------|-------------|-------------|
| `domain` | string | obligatorio | Dominio a investigar |
| `sources` | string | `duckduckgo,yahoo,hackertarget,crtsh,rapiddns,urlscan` | Fuentes separadas por coma |
| `limit` | integer | 200 | Máximo de resultados por fuente |

**Ejemplo:**
```
osint_domain("empresa.com")
osint_domain("empresa.com", sources="crtsh,hackertarget", limit=500)
```

---

### `osint_whois`

Consulta WHOIS de un dominio o IP. Devuelve: registrante, organización, emails de contacto, fechas de creación/expiración, nameservers, estado y DNSSEC.

**Parámetros:**
| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `target` | string | Dominio (`empresa.com`) o IP pública |

**Ejemplos:**
```
osint_whois("empresa.com")
osint_whois("8.8.8.8")
```

---

### `osint_dns`

Enumeración DNS completa de un dominio:
- Registros A, AAAA, MX, NS, TXT, SOA, CNAME
- Análisis de seguridad email: SPF, DMARC, DKIM
- Subdominios comunes: www, mail, vpn, admin, api, dev, staging...

**Parámetros:**
| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `domain` | string | Dominio a analizar |

**Ejemplo:**
```
osint_dns("empresa.com")
```

---

### `osint_phone`

Analiza un número de teléfono: valida el formato E.164, identifica país, operador (puede no ser exacto por portabilidad), tipo de línea y zona horaria.

**Parámetros:**
| Parámetro | Tipo | Por defecto | Descripción |
|-----------|------|-------------|-------------|
| `phone` | string | obligatorio | Número (ej: `+34612345678` o `612345678`) |
| `country` | string | `"US"` | Código de país ISO para números locales |

**Ejemplos:**
```
osint_phone("+34612345678")
osint_phone("612345678", country="ES")
osint_phone("+12125551234")
```

---

### `osint_ip`

Obtiene información de una IP pública: ASN, organización, país, ciudad, hostname inverso y abuse contact. Usa ipinfo.io (sin clave, 50k req/mes gratis) y WHOIS del sistema.

**Parámetros:**
| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `ip` | string | Dirección IP pública |

**Ejemplo:**
```
osint_ip("8.8.8.8")
```

---

### `osint_breach_check` — HaveIBeenPwned

Comprueba si un email aparece en brechas de datos conocidas usando la API v3 de [HaveIBeenPwned](https://haveibeenpwned.com).

Sin API key funciona con funcionalidad limitada (rate-limited). Con API key (~3,50€/mes) obtiene detalle completo de cada brecha.

**Parámetros:**
| Parámetro | Tipo | Por defecto | Descripción |
|-----------|------|-------------|-------------|
| `email` | string | obligatorio | Email a comprobar |
| `api_key` | string | `""` | API key de HIBP (opcional) |

**Ejemplo:**
```
osint_breach_check("usuario@ejemplo.com")
osint_breach_check("usuario@ejemplo.com", api_key="tu-clave-hibp")
```

---

### `osint_dossier`

Genera un dossier OSINT completo sobre un objetivo combinando múltiples herramientas según el tipo. Guarda el resultado como fichero Markdown en `OSINT_VAULT`.

**Parámetros:**
| Parámetro | Tipo | Por defecto | Descripción |
|-----------|------|-------------|-------------|
| `target` | string | obligatorio | Username, email, dominio, IP o teléfono |
| `target_type` | string | `"domain"` | Tipo: `person`, `email`, `company`, `domain`, `ip`, `phone` |
| `save` | boolean | `true` | Guardar en `OSINT_VAULT` |

**Qué ejecuta según tipo:**

| Tipo | Herramientas que combina |
|------|--------------------------|
| `person` | Sherlock + Maigret |
| `email` | Holehe + HIBP + WHOIS del dominio + DNS |
| `company` / `domain` | WHOIS + DNS + TheHarvester |
| `ip` | osint_ip |
| `phone` | osint_phone |

**Ejemplos:**
```
osint_dossier("johndoe", target_type="person")
osint_dossier("usuario@empresa.com", target_type="email")
osint_dossier("empresa.com", target_type="company")
osint_dossier("8.8.8.8", target_type="ip")
```

---

## Flujo de trabajo recomendado

### Investigación de dominio/empresa

```
1. osint_status          → verificar herramientas disponibles
2. osint_whois(dominio)  → propietario, fechas, registrar
3. osint_dns(dominio)    → infraestructura, seguridad email
4. osint_domain(dominio) → emails, subdominios, empleados
   → Si se encuentran emails: osint_breach_check(email)
   → Si se encuentran IPs: osint_ip(ip)
```

### Investigación de persona

```
1. osint_social_scan(username)  → resultado rápido en redes sociales
2. osint_username(username)     → búsqueda profunda en 3000+ sitios
   → Si se encuentra email: osint_email(email) + osint_breach_check(email)
```

### Generar informe completo

```
osint_dossier("objetivo", target_type="company")
```

El informe se guarda como Markdown en `OSINT_VAULT` con nombre `YYYY-MM-DD_company_objetivo.md`.

---

## Límites y consideraciones

- **maigret:** Puede generar muchas peticiones HTTP. Algunos sitios bloquean IPs con mucho tráfico.
- **holehe:** Algunos servicios cambian su interfaz de recuperación de contraseña con frecuencia y pueden dar falsos negativos.
- **theHarvester:** Las fuentes de búsqueda (Google, Bing) tienen rate-limiting agresivo. Las fuentes recomendadas por defecto (`crtsh`, `hackertarget`, `urlscan`) son más estables.
- **HIBP:** Sin API key las peticiones están muy limitadas (1 req/1,5s). Con API key se elimina el rate-limit.
- **ipinfo.io:** 50.000 peticiones/mes en el plan gratuito. Para uso intensivo considera una API key.
