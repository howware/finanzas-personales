"""La guardia detecta datos reales. Los valores se generan al correr la prueba para no dejarlos en el repo."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import check_private_data as guard  # noqa: E402


def card() -> str:
    base = "4" + "1" * 14
    return base + next(str(d) for d in range(10) if guard.luhn(base + str(d)))


def clabe() -> str:
    base = "012180" + "0" * 2 + "123456789"
    return base + next(str(d) for d in range(10) if guard.clabe(base + str(d)))


class GuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, name: str, text: str = "") -> list[str]:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return guard.findings(path)

    def test_detects_identifiers_without_printing_them(self):
        found = self.check("a.txt", f"tarjeta {card()}\nclabe {clabe()}\ncorreo ana" + "@" + "correo.mx\n"
                                    "rfc " + "ABCD" + "800101" + "AB1\n")
        kinds = " ".join(found)
        for kind in ("tarjeta", "CLABE", "correo", "RFC"):
            self.assertIn(kind, kinds)
        self.assertNotIn(card(), kinds)

    def test_blocks_real_data_locations_and_files(self):
        self.assertTrue(self.check("estados/2026-09.jsonl"))
        self.assertTrue(self.check(".memory/memory.sqlite"))
        self.assertTrue(self.check("estado.pdf"))

    def test_ignores_hashes_ids_and_amounts(self):
        text = ('{"file_sha256": "912184de982dded72a3e0cd64db0cf9845826d870b1c258736f5d2939629d4f9", '
                '"id": "TX_08850ce3ad1b003a", "amount": "-1200.00", "user": "dev@example.com"}')
        self.assertEqual(self.check("ok.json", text), [])

    def test_repository_is_clean(self):
        root = Path(__file__).resolve().parents[1]
        # CI checks out the adapters inside the workspace; they are other repositories with their own guards
        others = {"long-term-memory-for-AI", "mx-bank-statement-reader"}
        files = [p for p in root.rglob("*") if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts
                 and p.relative_to(root).parts[0] not in others]
        self.assertEqual([f for p in files for f in guard.findings(p.relative_to(root))
                          if not str(p.relative_to(root)).startswith(("estados", "reportes", ".memory"))], [])


if __name__ == "__main__":
    unittest.main()
