# MCP Obsidian — Documentación

Servidor MCP para acceder al vault de [Obsidian](https://obsidian.md) directamente desde Claude Code.

## Instalación

```bash
pip install mcp
```

## Configuración

### Variable de entorno obligatoria

```bash
export OBSIDIAN_VAULT=/ruta/a/tu/vault
```

Si no se define, el servidor usa `~/Obsidian` como valor por defecto.

### Añadir a Claude Code (`~/.claude.json`)

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

O con conda/venv:
```json
{
  "mcpServers": {
    "harper-obsidian": {
      "type": "stdio",
      "command": "/home/tuusuario/.conda/envs/mcp/bin/python",
      "args": ["/ruta/a/harper-mcps/mcp_obsidian_server.py"],
      "env": {
        "OBSIDIAN_VAULT": "/home/tuusuario/Obsidian"
      }
    }
  }
}
```

---

## Herramientas

### `search_vault`

Busca texto en todas las notas del vault. Devuelve las notas que contienen la búsqueda con un fragmento de contexto (±100 caracteres alrededor del match).

**Parámetros:**
| Parámetro | Tipo | Por defecto | Descripción |
|-----------|------|-------------|-------------|
| `query` | string | obligatorio | Texto a buscar |
| `max_results` | integer | 20 | Máximo de resultados |

**Ejemplo:**
```
search_vault("reunión cliente", max_results=10)
```

---

### `read_note`

Lee una nota del vault. La ruta es relativa al raíz del vault.

**Parámetros:**
| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `path` | string | Ruta relativa al vault (ej: `Proyectos/mi-nota.md`) |

**Devuelve:** Frontmatter parseado + contenido completo de la nota.

**Ejemplo:**
```
read_note("00-Index/inicio.md")
read_note("06-Janet/red/spider.md")
```

---

### `write_note`

Escribe o sobreescribe una nota. Crea los directorios intermedios si no existen.

**Parámetros:**
| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `path` | string | Ruta relativa al vault destino |
| `content` | string | Contenido completo de la nota |

**Ejemplo:**
```
write_note("Diario/2026-05-14.md", "# Hoy\n\nApuntes del día...")
```

---

### `list_notes`

Lista notas de un directorio (recursivo). Sin argumento lista todo el vault.

**Parámetros:**
| Parámetro | Tipo | Por defecto | Descripción |
|-----------|------|-------------|-------------|
| `directory` | string | `""` (raíz) | Subdirectorio del vault |

**Ejemplo:**
```
list_notes("02-Proyectos")
list_notes()   # todo el vault
```

---

### `find_by_tag`

Busca notas que contengan un tag, tanto en el frontmatter YAML como en el cuerpo (`#tag`).

**Parámetros:**
| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `tag` | string | Tag a buscar (con o sin `#`) |

**Ejemplo:**
```
find_by_tag("pendiente")
find_by_tag("#proyecto")
```

---

### `get_backlinks`

Encuentra todas las notas que enlazan a la nota indicada mediante la sintaxis `[[nombre]]` de Obsidian.

**Parámetros:**
| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `path` | string | Ruta relativa de la nota objetivo |

**Ejemplo:**
```
get_backlinks("00-Index/inicio.md")
```

---

### `vault_structure`

Devuelve el árbol de directorios del vault con el número de notas en cada carpeta.

**Ejemplo de salida:**
```
Vault: /home/usuario/Obsidian
Total: 342 notas

   12 notas — 00-Index
   87 notas — 01-Conversaciones
   45 notas — 02-Proyectos
  ...
```

---

## Integración con Meilisearch (opcional)

Si tienes [Meilisearch](https://www.meilisearch.com/) disponible en tu red, puedes complementar este servidor con un indexador que sincronice el vault cada N minutos. Consulta la [documentación de Meilisearch](https://www.meilisearch.com/docs) para configurarlo.

El servidor `mcp_obsidian_server.py` incluido hace búsqueda de texto plano directamente en los ficheros. Para búsqueda semántica y tolerante a errores tipográficos, Meilisearch es la opción recomendada.

---

## Estructura del frontmatter soportada

El servidor parsea frontmatter YAML básico (clave: valor en líneas separadas):

```yaml
---
fecha: 2026-05-14
tags: [proyecto, pendiente]
autor: nombre
---
```

Para frontmatter YAML complejo (arrays multilínea, valores anidados) se recomienda añadir el módulo `PyYAML`:
```bash
pip install pyyaml
```
Y adaptar la función `_parse_frontmatter` para usar `yaml.safe_load()`.
