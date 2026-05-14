#!/usr/bin/env python3
"""
MCP server for Obsidian vault access from Claude Code.

Configure the vault path via environment variable:
  export OBSIDIAN_VAULT=/path/to/your/vault

Requires: pip install mcp
"""
import os
import re
import json
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

# Configure via environment variable — fallback to ~/Obsidian
VAULT = Path(os.environ.get("OBSIDIAN_VAULT", str(Path.home() / "Obsidian")))

mcp = FastMCP("harper-obsidian")


def _rel(path: Path) -> str:
    return str(path.relative_to(VAULT))


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm_block = text[3:end].strip()
    body = text[end + 4:].lstrip("\n")
    meta = {}
    for line in fm_block.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
    return meta, body


def _all_notes() -> list[Path]:
    return sorted(VAULT.rglob("*.md"))


# ──────────────────────────────────────────────
# Tools
# ──────────────────────────────────────────────

@mcp.tool()
def search_vault(query: str, max_results: int = 20) -> str:
    """
    Search text across all notes in the vault.
    Returns a list of matching notes with a context snippet.
    """
    query_lower = query.lower()
    results = []
    for note in _all_notes():
        try:
            text = note.read_text(errors="replace")
        except Exception:
            continue
        if query_lower in text.lower():
            idx = text.lower().find(query_lower)
            start = max(0, idx - 80)
            end = min(len(text), idx + 120)
            snippet = text[start:end].replace("\n", " ").strip()
            results.append(f"**{_rel(note)}**\n  …{snippet}…")
        if len(results) >= max_results:
            break
    if not results:
        return f"No results for '{query}'."
    return f"{len(results)} result(s) for '{query}':\n\n" + "\n\n".join(results)


@mcp.tool()
def read_note(path: str) -> str:
    """
    Read a note from the vault. 'path' is relative to the vault root.
    Example: '06-Projects/my-note.md'
    Returns parsed frontmatter + full content.
    """
    target = VAULT / path
    if not target.exists():
        return f"Note not found: {path}"
    text = target.read_text(errors="replace")
    meta, body = _parse_frontmatter(text)
    out = f"# {path}\n"
    if meta:
        out += "**Frontmatter:** " + " | ".join(f"{k}: {v}" for k, v in meta.items()) + "\n\n"
    out += body
    return out


@mcp.tool()
def write_note(path: str, content: str) -> str:
    """
    Write or overwrite a note in the vault.
    'path' is relative to the vault root.
    Creates parent directories if they don't exist.
    """
    target = VAULT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return f"Note saved: {path} ({len(content)} bytes)"


@mcp.tool()
def list_notes(directory: str = "") -> str:
    """
    List notes in a vault directory (recursive).
    Without argument, lists the entire vault.
    """
    base = VAULT / directory if directory else VAULT
    if not base.exists():
        return f"Directory not found: {directory}"
    notes = sorted(base.rglob("*.md"))
    if not notes:
        return "No notes in that directory."
    lines = [f"- {_rel(n)}" for n in notes]
    return f"{len(notes)} note(s) in '{directory or '(vault root)'}'\n\n" + "\n".join(lines)


@mcp.tool()
def find_by_tag(tag: str) -> str:
    """
    Find notes that contain a tag in their frontmatter or body (#tag).
    """
    tag_clean = tag.lstrip("#").lower()
    results = []
    for note in _all_notes():
        try:
            text = note.read_text(errors="replace")
        except Exception:
            continue
        meta, body = _parse_frontmatter(text)
        tags_fm = meta.get("tags", "")
        if tag_clean in tags_fm.lower() or f"#{tag_clean}" in body.lower():
            results.append(_rel(note))
    if not results:
        return f"No notes with tag '{tag}'."
    return f"{len(results)} note(s) with tag '{tag}':\n\n" + "\n".join(f"- {r}" for r in results)


@mcp.tool()
def get_backlinks(path: str) -> str:
    """
    Find all notes that link to the given note (backlinks).
    'path' is relative to the vault root.
    """
    target_name = Path(path).stem
    pattern_bare = f"[[{target_name}]]"
    pattern_path = f"[[{path}]]"
    results = []
    for note in _all_notes():
        if _rel(note) == path:
            continue
        try:
            text = note.read_text(errors="replace")
        except Exception:
            continue
        if pattern_bare in text or pattern_path in text or f"[[{target_name}|" in text:
            results.append(_rel(note))
    if not results:
        return f"No notes link to '{path}'."
    return f"{len(results)} backlink(s) to '{path}':\n\n" + "\n".join(f"- {r}" for r in results)


@mcp.tool()
def vault_structure() -> str:
    """
    Returns the directory structure of the vault with note counts per folder.
    """
    dirs: dict[str, int] = {}
    for note in _all_notes():
        folder = str(note.parent.relative_to(VAULT)) if note.parent != VAULT else "(root)"
        dirs[folder] = dirs.get(folder, 0) + 1
    lines = [f"  {count:3d} notes — {folder}" for folder, count in sorted(dirs.items())]
    total = sum(dirs.values())
    return f"Vault: {VAULT}\nTotal: {total} notes\n\n" + "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
