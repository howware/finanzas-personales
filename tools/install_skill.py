"""Instala el skill finanzas-personales para Claude Code o Codex.

    python tools/install_skill.py                                   # ~/.claude/skills/finanzas-personales
    python tools/install_skill.py --target ~/.codex/skills/finanzas-personales

Copia SKILL.md y scripts/. Reinstalar reemplaza el skill y nunca toca tus datos (la memoria vive en la
carpeta de tus finanzas, no aquí).
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "skill" / "finanzas-personales"
DEFAULT = Path.home() / ".claude" / "skills" / "finanzas-personales"


def main() -> int:
    parser = argparse.ArgumentParser(description="Instala el skill finanzas-personales")
    parser.add_argument("--target", default=str(DEFAULT), help=f"Carpeta destino (por omisión {DEFAULT})")
    target = Path(parser.parse_args().target).expanduser()
    if target.name != "finanzas-personales":
        print(f"El destino debe terminar en finanzas-personales: {target}", file=sys.stderr)
        return 2
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(SOURCE, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    print(f"Skill instalado en {target}")
    print("Requiere también los skills mxbank (>= 0.2.0) y project-memory (>= 0.3.0).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
