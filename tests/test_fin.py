"""Pruebas de fin.py contra una memoria real (helper de project-memory) y JSON sintéticos de mxbank.

El helper se busca en FIN_MEMORY_HELPER, en ../long-term-memory-for-AI/db/memory.py o en el skill instalado.
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIN = ROOT / "skill" / "finanzas-personales" / "scripts" / "fin.py"
FIXTURES = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(FIN.parent))
import fin  # noqa: E402


def find_helper() -> Path | None:
    for c in (os.environ.get("FIN_MEMORY_HELPER"), ROOT.parent / "long-term-memory-for-AI" / "db" / "memory.py",
              Path.home() / ".claude/skills/project-memory/scripts/memory.py"):
        if c and Path(c).is_file():
            return Path(c)
    return None


HELPER = find_helper()
BY = "person:test"


@unittest.skipUnless(HELPER, "No se encontró memory.py de project-memory")
class FinTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "memory.sqlite")
        self.mem([ "init", "--owner-name", "Test", "--owner-key", BY])
        self.assertTrue(self.fin("setup", "--by", BY)["ok"])

    def tearDown(self):
        self.tmp.cleanup()

    def mem(self, args: list[str]) -> dict:
        out = subprocess.run([sys.executable, str(HELPER), "--db", self.db, *args], capture_output=True, text=True,
                             encoding="utf-8", check=True).stdout
        return json.loads(out)

    def fin(self, *args: str, ok: bool = True) -> dict:
        proc = subprocess.run([sys.executable, str(FIN), "--mem", str(HELPER), "--db", self.db, "--tz=-06:00", *args],
                              capture_output=True, text=True, encoding="utf-8")
        result = json.loads(proc.stdout)
        if ok:
            self.assertEqual(proc.returncode, 0, result)
        return result

    def fixture(self, name: str) -> str:
        return str(FIXTURES / f"{name}.json")

    def tx_key(self, classifier: str) -> str:
        rows = self.mem(["list", "--event-type", "transaction", "--where", f"link:classified_by = {classifier}",
                         "--column", "key"])["rows"]
        return rows[0]["key"]

    # -- importación ------------------------------------------------------------
    def test_import_and_reimport_do_not_duplicate(self):
        first = self.fin("import", self.fixture("credit_m0"), self.fixture("bbva_debit"), "--by", BY)
        self.assertEqual(sorted(s["transactions_new"] for s in first["statements"]), [7, 9])
        again = self.fin("import", self.fixture("credit_m0"), self.fixture("bbva_debit"), "--by", BY)
        self.assertEqual([s["transactions_new"] for s in again["statements"]], [0, 0])
        self.assertEqual(sorted(s["transactions_existing"] for s in again["statements"]), [7, 9])
        count = self.mem(["aggregate", "--event-type", "transaction"])["groups"][0]["value"]
        self.assertEqual(count, 16)

    def test_payment_due_settled_in_any_order(self):
        newer = self.fin("import", self.fixture("credit_m1"), "--by", BY)
        self.assertEqual(len(newer["pending"]), 1)
        older = self.fin("import", self.fixture("credit_m0"), "--by", BY)
        settled = older["statements"][0]["payments_settled"]
        self.assertEqual(settled[0]["covered"], True)
        self.assertEqual(older["statements"][0]["older_than_current"], 4)
        pending = self.mem(["pending"])
        self.assertEqual([p["event_key"] for p in pending], ["DUE_" + json.loads(Path(self.fixture("credit_m1")).read_text(encoding="utf-8"))["statement_id"]])
        balance = self.mem(["list", "--entity-type", "account", "--where", "fact:account_product = credit", "--as-of", "2100-01-01",
                            "--column", "fact:balance/since"])["rows"][0]["fact:balance/since"]
        self.assertEqual(str(balance)[:10], "2026-10-14")

    def test_rejects_json_without_stable_key(self):
        st = json.loads(Path(self.fixture("credit_m0")).read_text(encoding="utf-8"))
        st["privacy"]["pseudonym_scope"] = "run"
        path = Path(self.tmp.name) / "nokey.json"
        path.write_text(json.dumps(st), encoding="utf-8")
        result = self.fin("import", str(path), "--by", BY, ok=False)
        self.assertFalse(result["ok"])
        self.assertIn("--pseudonym-key-env", result["error"]["message"])
        self.assertEqual(result["error"]["code"], 2)

    def test_rejects_old_schema(self):
        st = json.loads(Path(self.fixture("credit_m0")).read_text(encoding="utf-8"))
        st["schema_version"] = "1.0"
        path = Path(self.tmp.name) / "old.json"
        path.write_text(json.dumps(st), encoding="utf-8")
        self.assertIn("schema 1.1", self.fin("import", str(path), "--by", BY, ok=False)["error"]["message"])

    def test_unreadable_input_is_a_clear_error(self):
        broken = Path(self.tmp.name) / "broken.json"
        broken.write_text('{"ok": true, "statement_id": ', encoding="utf-8")
        for path in (str(broken), str(Path(self.tmp.name) / "missing.json")):
            proc = subprocess.run([sys.executable, str(FIN), "--mem", str(HELPER), "--db", self.db, "import", path,
                                   "--by", BY], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(proc.returncode, 2, proc.stderr)
            self.assertEqual(json.loads(proc.stdout)["error"]["code"], 2)
            self.assertNotIn("Traceback", proc.stderr)

    def test_ndjson_input(self):
        lines = [json.dumps(json.loads(Path(self.fixture(n)).read_text(encoding="utf-8"))) for n in ("bancoppel", "bbva_debit")]
        path = Path(self.tmp.name) / "batch.jsonl"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = self.fin("import", str(path), "--by", BY)
        self.assertEqual(len(result["statements"]), 2)

    # -- categorías y reporte -------------------------------------------------------
    def test_rules_overrides_cash_budget_report(self):
        self.fin("import", self.fixture("credit_m0"), self.fixture("bbva_debit"), "--by", BY)
        result = self.fin("import", self.fixture("credit_m0"), "--by", BY)
        self.assertIn("merchant:oxxo", [t["classifier"] for t in result["to_classify"]])
        self.fin("add-category", "--key", "category:food/groceries", "--name", "Groceries", "--alias", "Súper", "--by", BY)
        self.fin("categorize", "--rule", "merchant:oxxo=category:food/groceries",
                 "--rule", "merchant:netflix=category:subscriptions/general",
                 "--rule", "merchant:amazon=category:personal-shopping/general",
                 "--rule", "kind:spei_in=category:income/salary", "--by", BY)
        amazon = self.tx_key("merchant:amazon")
        self.fin("recategorize", amazon, "--to", "category:other/general", "--by", BY)
        replaced = self.fin("recategorize", amazon, "--to", "category:entertainment/general", "--by", BY)
        self.assertEqual(len(replaced["replaced"]), 1)
        cash = self.fin("expense", "--amount", "180.50", "--description", "Fonda Doña Mary", "--date", "2026-08-20",
                        "--classifier", "merchant:oxxo", "--by", BY)
        self.assertTrue(cash["created"])
        self.assertFalse(self.fin("expense", "--amount", "180.50", "--description", "Fonda Doña Mary",
                                  "--date", "2026-08-20", "--classifier", "merchant:oxxo", "--by", BY)["created"])
        self.fin("budget", "--category", "category:food/groceries", "--amount", "4000", "--month", "2026-08", "--by", BY)
        report = self.fin("report", "--month", "2026-08")
        by_cat = {c["category"]: c for c in report["categories"]}
        self.assertEqual(by_cat["category:food"]["net_cents"], -15000 - 18050)
        self.assertEqual(by_cat["category:food"]["budget"], "$4,000.00")
        self.assertEqual(by_cat["category:food"]["budget_left"], "$3,669.50")
        self.assertEqual(by_cat["category:entertainment"]["net_cents"], -120000)
        self.assertNotIn("category:personal-shopping", by_cat)
        self.assertNotIn("category:internal", by_cat)
        self.assertEqual(report["income"], "$16,000.00")
        # el pago a la tarjeta (13,000) y el retiro OXXO CASH no son gasto
        self.assertNotIn(-1300000, [c["net_cents"] for c in report["categories"]])
        july = self.fin("report", "--month", "2026-07")
        self.assertEqual(july["categories"], [])
        self.assertEqual(july["budgets_without_spending"], [])

    def test_budget_history_and_recipes_use_overrides(self):
        self.fin("import", self.fixture("credit_m0"), self.fixture("credit_m1"), "--by", BY)
        self.fin("categorize", "--rule", "merchant:oxxo=category:food/general",
                 "--rule", "merchant:amazon=category:personal-shopping/general", "--by", BY)
        self.fin("budget", "--category", "category:food/general", "--amount", "3000", "--month", "2026-07", "--by", BY)
        self.fin("budget", "--category", "category:food/general", "--amount", "4000", "--month", "2026-09", "--by", BY)
        aug = {c["category"]: c for c in self.fin("report", "--month", "2026-08")["categories"]}
        sep = {c["category"]: c for c in self.fin("report", "--month", "2026-09")["categories"]}
        self.assertEqual(aug["category:food"]["budget"], "$3,000.00")
        self.assertEqual(sep["category:food"]["budget"], "$4,000.00")
        self.fin("recategorize", self.tx_key("merchant:amazon"), "--to", "category:entertainment/general", "--by", BY)
        result = self.mem(["recipe", "run", "recipe:spending-by-category", "--param", "start=2026-08-01",
                           "--param", "end=2026-09-01"])
        groups = {g[next(k for k in g if k.startswith("first("))]: g["value"]
                  for g in result.get("result", result)["groups"]}
        self.assertEqual(groups["Entertainment"], -120000)
        self.assertNotIn("Personal shopping", groups)

    def test_only_subcategories_can_be_created_or_targeted(self):
        self.assertFalse(self.fin("add-category", "--key", "category:pets", "--name", "Pets", "--by", BY, ok=False)["ok"])
        self.assertFalse(self.fin("categorize", "--rule", "merchant:x=category:food", "--by", BY, ok=False)["ok"])


class UnitTest(unittest.TestCase):
    def test_merchant_name(self):
        self.assertEqual(fin.merchant_name("OXXO", "OXXO CENTRO MTY"), "OXXO")
        self.assertEqual(fin.merchant_name(None, "TACOS [DATO]"), "TACOS")
        self.assertEqual(fin.merchant_name(None, "OXXO SUC 1234 CD JUAREZ"), "OXXO JUAREZ")
        self.assertIsNone(fin.merchant_name(None, "[DATO] 1234"))

    def test_cents_and_money(self):
        self.assertEqual(fin.cents("-1200.00"), -120000)
        self.assertEqual(fin.cents("0.005"), 1)
        self.assertEqual(fin.money(-123456), "-$1,234.56")

    def test_classifier(self):
        seed = fin.load_seed()
        self.assertEqual(fin.classifier({"type": "card_payment", "description": "BMOVIL.PAGO TDC"}, seed)[0],
                         "kind:card_payment")
        self.assertEqual(fin.classifier({"type": "spei_out", "counterparty_ref": "PERSONA_1a2b"}, seed)[0],
                         "counterparty:PERSONA_1a2b")
        self.assertEqual(fin.classifier({"type": "spei_out", "description": "SPEI ENVIADO"}, seed)[0], "kind:spei_out")
        self.assertEqual(fin.classifier({"type": "cash_withdrawal", "merchant": "OXXO"}, seed)[0], "kind:cash_withdrawal")
        self.assertEqual(fin.classifier({"type": "card_purchase", "merchant": "NETFLIX"}, seed)[0], "merchant:netflix")


if __name__ == "__main__":
    unittest.main()
