"""Conformidad con la especificación howware 0.2 (https://howware.org): manifiesto, versiones y protocolo."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "howware.json").read_text(encoding="utf-8"))
SKILL = ROOT / MANIFEST["skill"]


class ManifestTest(unittest.TestCase):
    def test_required_fields(self):
        for field in ("howware", "name", "version", "description", "license", "hosts", "skill", "tools", "memory",
                      "privacy"):
            self.assertIn(field, MANIFEST)
        for key in ("stays_local", "agent_sees", "cannot_guarantee"):
            self.assertTrue(MANIFEST["privacy"][key], key)

    def test_versions_match_the_code(self):
        out = subprocess.run([sys.executable, str(SKILL / "scripts" / "fin.py"), "--version"],
                             capture_output=True, text=True).stdout
        self.assertEqual(out.split()[-1], MANIFEST["version"])
        seed = json.loads((SKILL / "scripts" / "seed.json").read_text(encoding="utf-8"))
        self.assertEqual(seed["seed_version"], MANIFEST["memory"]["seed_version"])

    def test_tools_declare_no_network(self):
        for tool in MANIFEST["tools"]:
            source = (SKILL / "scripts" / tool["name"]).read_text(encoding="utf-8")
            self.assertFalse(re.search(r"^\s*(import|from)\s+(socket|urllib|http|requests)\b", source, re.M))
            self.assertFalse(tool["network"])

    def test_module_version_matches(self):
        out = subprocess.run([sys.executable, str(SKILL / "scripts" / "compromisos.py"), "--version"],
                             capture_output=True, text=True).stdout
        self.assertEqual(out.split()[-1], MANIFEST["version"])


class ProtocolTest(unittest.TestCase):
    def test_required_sections(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\nname: " + MANIFEST["name"]))
        for heading in ("Reglas", "Arranque", "Frontera de la exactitud", "Aprobación", "Presentar resultados"):
            self.assertRegex(text, rf"(?m)^## (\d+\. )?{heading}", heading)
        self.assertGreaterEqual(len(re.findall(r"(?m)^## \d+\. ", text)), 6, "workflows")

    def test_module_protocol(self):
        text = (SKILL / "compromisos.md").read_text(encoding="utf-8")
        for heading in ("Reglas del módulo", "Frontera de la exactitud", "Aprobación"):
            self.assertRegex(text, rf"(?m)^## {heading}", heading)
        self.assertIn("El plan se reajusta, no se rompe", text)

    def test_conversation_scenarios_exist(self):
        rows = [line for line in (ROOT / "tests" / "conversations.md").read_text(encoding="utf-8").splitlines()
                if re.match(r"\| \d+ \|", line)]
        self.assertGreaterEqual(len(rows), 8)


if __name__ == "__main__":
    unittest.main()
