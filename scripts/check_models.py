"""Fail if any model name other than the pinned one appears in the project.

Scans every text file under the project root (including the sample mailbox and
the frontend source) except .env, .venv/, node_modules/, dist/, __pycache__/ and
.git/. Binary files (the SQLite databases, .xlsx) are skipped. Exits 1 and lists each hit if it finds a model-name
pattern that is not the allowed model; exits 0 otherwise.

Each pattern spells the name with a one-letter character class (e.g. gp[t]) so
this file does not match itself and contains no model names of its own.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = "gpt-6-luna"
EXCLUDE_DIRS = {".venv", "__pycache__", ".git", "node_modules", "dist", ".pytest_cache"}
EXCLUDE_FILES = {".env"}

PATTERNS = [
    r"\bgp[t]-?\d[\w.\-]*",  # gpt-<n>... family
    r"\bgp[t]-[a-z][\w.\-]*",  # gpt-<word>...
    r"\bchatgp[t][\w.\-]*",
    r"\bclaud[e]-[\w.\-]+",  # claude-<anything>
    r"\bclaud[e][ _](opus|sonnet|haiku|instant)[\w.\-]*",
    r"\b(opu[s]|sonne[t]|haik[u])[- ]?\d[\w.\-]*",
    r"\bgemin[i][- ]?[\d.]+[\w.\-]*",
    r"\bgemin[i]-[a-z][\w.\-]*",
    r"\bgemm[a][- ]?\d[\w.\-]*",
    r"\bllam[a][- ]?\d[\w.\-]*",
    r"\b(mis[t]ral|mix[t]ral|codes[t]ral)[\w.\-]*",
    r"\bdeepsee[k][\w.\-]*",
    r"\bqwe[n][\w.\-]*",
    r"\bgro[k]-\d[\w.\-]*",
    r"\bo[1345]-(min[i]|pr[o]|previe[w])\b",
    r"\btext-davinc[i][\w.\-]*",
]
REGEX = re.compile("|".join(f"(?:{p})" for p in PATTERNS), re.IGNORECASE)


def scan() -> list[tuple[str, int, str]]:
    hits = []
    for path in sorted(ROOT.rglob("*")):
        rel = path.relative_to(ROOT)
        if not path.is_file() or path.name in EXCLUDE_FILES or set(rel.parts) & EXCLUDE_DIRS:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary file
        for lineno, line in enumerate(text.splitlines(), 1):
            for m in REGEX.finditer(line):
                if m.group(0).rstrip(".-").lower() != ALLOWED:
                    hits.append((str(rel), lineno, m.group(0)))
    return hits


def main() -> int:
    files = [p for p in ROOT.rglob("*") if p.is_file() and p.name not in EXCLUDE_FILES
             and not set(p.relative_to(ROOT).parts) & EXCLUDE_DIRS]
    allowed_count = sum(p.read_text(encoding="utf-8", errors="ignore").count(ALLOWED) for p in files)
    hits = scan()
    print(f"Scanned {len(files)} files under {ROOT.name}/ (excluding .env, .venv/, node_modules/, dist/, __pycache__/, .git/)")
    print(f"Allowed model: {ALLOWED} ({allowed_count} occurrences)")
    if hits:
        print(f"FAIL: {len(hits)} other model name(s) found:")
        for rel, lineno, name in hits:
            print(f"  {rel}:{lineno}: {name}")
        return 1
    print("PASS: no other model names found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
