"""Guardia: ningún archivo versionado puede traer estados de cuenta ni datos que identifiquen a alguien.

    git ls-files -z | xargs -0 python tools/check_private_data.py      # lo que corre CI
    python tools/check_private_data.py archivo1 archivo2 ...

Bloquea PDFs, carpetas de datos reales (estados/, reportes/, .memory/), bases SQLite, CLABEs (con dígito
verificador), tarjetas (Luhn), RFC, CURP y correos. Los JSON de prueba vienen de PDFs sintéticos de mxbank.
Sale con 1 si encuentra algo; nunca imprime el valor encontrado, solo el archivo, la línea y el tipo.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

BLOCKED_PARTS = {"estados", "reportes", ".memory", "corpus"}
BLOCKED_SUFFIXES = {".pdf", ".sqlite", ".sqlite3", ".db"}
DIGITS = re.compile(r"(?<![\dA-Fa-f])\d{15,18}(?![\dA-Fa-f])")
RFC = re.compile(r"\b[A-ZÑ&]{3,4}\d{6}[A-Z\d]{3}\b")
CURP = re.compile(r"\b[A-Z][AEIOUX][A-Z]{2}\d{6}[HM][A-Z]{5}[A-Z\d]\d\b")
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")
EMAIL_OK = re.compile(r"@(example\.(com|org)|users\.noreply\.github\.com)$")


def luhn(number: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(number)):
        d = int(ch) * (2 if i % 2 else 1)
        total += d - 9 if d > 9 else d
    return total % 10 == 0


def clabe(number: str) -> bool:
    weights = [3, 7, 1] * 6
    check = (10 - sum(int(d) * w % 10 for d, w in zip(number[:17], weights)) % 10) % 10
    return check == int(number[17])


def findings(path: Path) -> list[str]:
    out = []
    if BLOCKED_PARTS & set(path.parts):
        out.append(f"{path}: carpeta de datos reales")
    if path.suffix.lower() in BLOCKED_SUFFIXES:
        out.append(f"{path}: tipo de archivo bloqueado ({path.suffix})")
    if out or not path.is_file():
        return out
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return out
    for n, line in enumerate(text.splitlines(), 1):
        for m in DIGITS.finditer(line):
            digits = m.group()
            if len(digits) == 18 and clabe(digits):
                out.append(f"{path}:{n}: posible CLABE")
            elif len(digits) in (15, 16) and luhn(digits):
                out.append(f"{path}:{n}: posible número de tarjeta")
        if RFC.search(line):
            out.append(f"{path}:{n}: posible RFC")
        if CURP.search(line):
            out.append(f"{path}:{n}: posible CURP")
        for m in EMAIL.finditer(line):
            if not EMAIL_OK.search(m.group()):
                out.append(f"{path}:{n}: correo electrónico")
    return out


def main(argv: list[str]) -> int:
    problems = [f for arg in argv for f in findings(Path(arg))]
    for p in problems:
        print(p, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
