"""Pruebas del módulo compromisos contra una memoria real (helper de project-memory) y JSON sintéticos de mxbank.

Los créditos, ingresos y pagos son inventados; los cargos que se ligan a un crédito vienen de los fixtures.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skill" / "finanzas-personales" / "scripts"
FIN, COMP = SCRIPTS / "fin.py", SCRIPTS / "compromisos.py"
FIXTURES = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(SCRIPTS))
import compromisos  # noqa: E402


def find_helper() -> Path | None:
    for c in (os.environ.get("FIN_MEMORY_HELPER"), ROOT.parent / "long-term-memory-for-AI" / "db" / "memory.py",
              Path.home() / ".claude/skills/project-memory/scripts/memory.py"):
        if c and Path(c).is_file():
            return Path(c)
    return None


HELPER = find_helper()
BY = "person:test"

TODAY = "2026-10-11"
DEBIT, CARD = "account:ACC_b6d0", "account:ACC_53ac"


def credit(**kw) -> dict:
    base = {"key": "credit:a", "name": "A", "rate_bp": 1200, "payment": 50000, "charges": 0, "day": 5,
            "remaining": None, "prepayment": True, "start": 100000}
    return {**base, **kw}


class AmortizationTest(unittest.TestCase):
    """Cálculo puro: sin memoria."""

    def test_monthly_interest_is_annual_rate_over_twelve(self):
        self.assertEqual(compromisos.interest(10000000, 1200), 100000)
        self.assertEqual(compromisos.interest(12345, 1000), 103)  # 102.875 → 103

    def test_schedule_until_payoff(self):
        sim = compromisos.simulate([credit()], date(2026, 10, 1), 0, "avalanche")
        months = sim["by_month"]
        self.assertEqual([months[m]["credit:a"]["balance"] for m in sorted(months)], [51000, 1510, 0])
        self.assertEqual(months["2026-12"]["credit:a"]["required"], 1525)
        self.assertEqual(sim["payoff"]["credit:a"], "2026-12")
        self.assertEqual(sim["interest"]["credit:a"], 1000 + 510 + 15)

    def test_payment_that_does_not_cover_interest_is_refused(self):
        with self.assertRaises(compromisos.FinError):
            compromisos.simulate([credit(payment=900)], date(2026, 10, 1), 0, "avalanche")

    def test_avalanche_and_snowball_choose_different_targets(self):
        high = credit(key="credit:high", name="High", rate_bp=1200, payment=1500000, start=90000000)
        small = credit(key="credit:small", name="Small", rate_bp=1000, payment=700000, start=45000000)
        first = {s: compromisos.simulate([high, small], date(2026, 10, 1), 300000, s)["by_month"]["2026-10"]
                 for s in ("avalanche", "snowball")}
        self.assertEqual(first["avalanche"]["credit:high"]["extra"], 300000)
        self.assertEqual(first["snowball"]["credit:small"]["extra"], 300000)

    def test_extra_payments_shorten_the_credit(self):
        base = compromisos.simulate([credit(start=1000000, payment=100000)], date(2026, 10, 1), 0, "avalanche")
        fast = compromisos.simulate([credit(start=1000000, payment=100000)], date(2026, 10, 1), 100000, "avalanche")
        self.assertLess(fast["payoff"]["credit:a"], base["payoff"]["credit:a"])
        self.assertLess(fast["interest"]["credit:a"], base["interest"]["credit:a"])

    def test_credit_without_rate_follows_its_calendar(self):
        sim = compromisos.simulate([credit(rate_bp=None, start=None, remaining=3)], date(2026, 10, 1), 0, "avalanche")
        self.assertEqual(sim["payoff"]["credit:a"], "2026-12")
        self.assertIsNone(sim["interest"]["credit:a"])

    def test_payment_already_made_this_month_is_not_counted_twice(self):
        sim = compromisos.simulate([credit()], date(2026, 10, 11), 0, "avalanche")
        self.assertEqual(sim["by_month"]["2026-10"]["credit:a"]["required"], 0)
        self.assertEqual(sim["by_month"]["2026-11"]["credit:a"]["required"], 50000)


@unittest.skipUnless(HELPER, "No se encontró memory.py de project-memory")
class CompromisosTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "memory.sqlite")
        self.mem(["init", "--owner-name", "Test", "--owner-key", BY])
        self.run_tool(FIN, "setup", "--by", BY)
        self.run_tool(FIN, "import", *(str(FIXTURES / f"{n}.json") for n in ("credit_m0", "credit_m1", "bbva_debit")),
                      "--by", BY)

    def tearDown(self):
        self.tmp.cleanup()

    def mem(self, args: list[str]) -> dict:
        out = subprocess.run([sys.executable, str(HELPER), "--db", self.db, *args], capture_output=True, text=True,
                             encoding="utf-8", check=True).stdout
        return json.loads(out)

    def run_tool(self, tool: Path, *args: str, ok: bool = True, today: str = TODAY) -> dict:
        extra = ["--today", today] if tool == COMP else []
        proc = subprocess.run([sys.executable, str(tool), "--mem", str(HELPER), "--db", self.db, "--tz=-06:00", *extra,
                               *args], capture_output=True, text=True, encoding="utf-8")
        result = json.loads(proc.stdout)
        if ok:
            self.assertEqual(proc.returncode, 0, result)
        return result

    def comp(self, *args: str, ok: bool = True, today: str = TODAY) -> dict:
        return self.run_tool(COMP, *args, "--by", BY, ok=ok, today=today)

    def mortgages(self) -> None:
        self.comp("activate")
        self.comp("credit", "--name", "Hipoteca BBVA", "--kind", "mortgage", "--lender", "BBVA", "--rate", "12",
                  "--payment", "12000", "--charges", "500", "--day", "5", "--balance", "900000",
                  "--balance-date", "2026-09-30", "--paid-with", DEBIT, "--prepayment", "yes", "--since", "2026-09-01")
        self.comp("credit", "--name", "Hipoteca Infonavit", "--kind", "mortgage", "--lender", "Infonavit",
                  "--rate", "10", "--payment", "6000", "--day", "20", "--balance", "450000",
                  "--balance-date", "2026-09-30", "--paid-with", CARD, "--prepayment", "yes", "--since", "2026-09-01")

    # -- activación ------------------------------------------------------------------
    def test_module_is_off_until_activated(self):
        result = self.comp("credit", "--name", "X", "--payment", "1", "--day", "1", "--remaining", "2", ok=False)
        self.assertEqual(result["error"]["code"], 2)
        self.assertIn("no está activo", result["error"]["message"])
        self.assertTrue(self.comp("activate")["active"])
        self.assertTrue(self.comp("activate")["active"])  # repetir no duplica

    def test_credit_without_rate_needs_remaining_payments(self):
        self.comp("activate")
        result = self.comp("credit", "--name", "Auto", "--payment", "8500", "--day", "10", ok=False)
        self.assertIn("--remaining", result["error"]["message"])
        self.assertEqual(self.comp("credit", "--name", "Auto", "--payment", "8500", "--day", "10",
                                   "--remaining", "36")["credit"], "credit:auto")

    def test_payment_below_interest_warns(self):
        self.comp("activate")
        result = self.comp("credit", "--name", "Mal", "--rate", "12", "--payment", "500", "--day", "1",
                           "--balance", "100000")
        self.assertTrue(result["warnings"])

    # -- pagos -------------------------------------------------------------------------
    def test_link_turns_charges_into_payments_and_settles_dues(self):
        self.mortgages()
        result = self.comp("link", "--classifier", "merchant:amazon", "--credit", "credit:hipoteca-infonavit")
        sync = result["sync"]
        self.assertEqual(sync["linked_payments"], 1)
        self.assertIn("DUE_hipoteca-infonavit_2026-10", sync["dues_created"])
        settled = {s["due"]: s for s in sync["dues_settled"]}
        self.assertFalse(settled["DUE_hipoteca-infonavit_2026-09"]["covered"])
        self.assertEqual(settled["DUE_hipoteca-infonavit_2026-09"]["shortfall"], "$4,800.00")
        again = self.comp("sync")
        self.assertEqual((again["linked_payments"], again["dues_created"], again["dues_settled"]), (0, [], []))

    def test_credit_without_rule_is_never_marked_unpaid(self):
        self.mortgages()
        sync = self.comp("sync")
        self.assertFalse([s for s in sync["dues_settled"] if "bbva" in s["due"]])
        self.assertIn("DUE_hipoteca-bbva_2026-09", [d["due"] for d in sync["overdue_unverified"]])

    def test_a_late_payment_settles_the_period_again(self):
        self.mortgages()
        self.comp("link", "--classifier", "merchant:amazon", "--credit", "credit:hipoteca-infonavit")
        result = self.comp("pay", "--credit", "credit:hipoteca-infonavit", "--amount", "4800", "--date", "2026-09-19")
        settled = {s["due"]: s for s in result["sync"]["dues_settled"]}
        self.assertTrue(settled["DUE_hipoteca-infonavit_2026-09"]["covered"])
        rows = self.mem(["list", "--event-type", "credit_due_settled", "--include-voided", "--column", "key"])["rows"]
        self.assertEqual(sorted(r["key"] for r in rows), ["PAID_DUE_hipoteca-infonavit_2026-09",
                                                          "PAID_DUE_hipoteca-infonavit_2026-09_2"])
        current = self.mem(["list", "--event-type", "credit_due_settled", "--column", "key"])["rows"]
        self.assertEqual([r["key"] for r in current], ["PAID_DUE_hipoteca-infonavit_2026-09_2"])

    def test_dues_appear_as_pending(self):
        self.mortgages()
        self.comp("sync")
        pending = json.dumps(self.mem(["pending"]))
        self.assertIn("DUE_hipoteca-bbva_2026-11", pending)

    # -- pronóstico ----------------------------------------------------------------------
    def test_forecast_converts_income_and_keeps_the_cushion_first(self):
        self.mortgages()
        self.comp("income", "--name", "Cliente", "--amount", "3000", "--currency", "USD")
        warned = self.comp("forecast")
        self.assertTrue(any("tipo de cambio" in w for w in warned["warnings"]))
        self.comp("fx", "--currency", "USD", "--rate", "18.50")
        self.comp("cushion", "--target", "50000", "--account", DEBIT)
        result = self.comp("forecast", "--horizon", "month")
        self.assertEqual(result["income_monthly"], "$55,500.00")
        self.assertEqual(result["cushion"]["gap"], "$42,550.00")
        margin = int(result["months"][0]["margin"].replace("$", "").replace(",", "").replace(".", ""))
        available = int(result["available_for_extra"].replace("$", "").replace(",", "").replace(".", ""))
        self.assertEqual(available, max(0, margin - 4255000))
        lower = self.comp("forecast", "--fx", "USD=17")
        self.assertEqual(lower["income_monthly"], "$51,000.00")

    def test_every_horizon_runs(self):
        self.mortgages()
        self.assertIn("week", self.comp("forecast", "--horizon", "week"))
        for horizon, months in (("quarter", 3), ("semester", 6), ("year", 12)):
            self.assertEqual(len(self.comp("forecast", "--horizon", horizon)["months"]), months)
        year = self.comp("forecast", "--horizon", "year")
        self.assertTrue(year["msi_ending"])

    def test_credit_payments_are_not_counted_as_spending(self):
        self.mortgages()
        before = self.comp("forecast")["pace"]["daily"]
        self.comp("link", "--classifier", "merchant:amazon", "--credit", "credit:hipoteca-infonavit")
        after = self.comp("forecast")["pace"]["daily"]
        self.assertNotEqual(before, after)

    # -- cascadas -----------------------------------------------------------------------------
    def test_commitment_paid_with_card_is_a_cascade(self):
        self.mortgages()
        cascades = self.comp("cascades")["cascades"]
        self.assertEqual(len(cascades), 1)
        self.assertEqual(cascades[0]["commitments"][0]["credit"], "Hipoteca Infonavit")
        self.assertFalse(cascades[0]["at_risk"])
        self.mem(["write", "--file", self.settlement(covered=False)])
        self.assertTrue(self.comp("cascades")["cascades"][0]["at_risk"])

    def settlement(self, covered: bool) -> str:
        path = Path(self.tmp.name) / "settled.json"
        path.write_text(json.dumps({
            "source": {"type": "import", "content": "test", "provided_by": BY, "captured_at": "now"},
            "performed_by": BY,
            "events": [{"key": "PAID_TEST", "type": "payment_due_settled", "occurred_at": "2026-11-08T12:00:00-06:00",
                        "summary": "test", "attributes": {"paid_amount": 100, "shortfall": 500000, "covered": covered},
                        "links": [{"predicate": "on_account", "entity": CARD}]}]}), encoding="utf-8")
        return str(path)

    # -- plan ---------------------------------------------------------------------------------
    def test_plan_compares_strategies_and_saves_a_version(self):
        self.mortgages()
        both = self.comp("plan", "--extra", "3000")
        self.assertEqual(set(both["strategies"]), {"avalanche", "snowball"})
        self.assertGreater(both["strategies"]["avalanche"]["months_saved"], 0)
        refused = self.comp("plan", "--extra", "3000", "--save", ok=False)
        self.assertIn("--strategy", refused["error"]["message"])
        saved = self.comp("plan", "--strategy", "avalanche", "--extra", "3000", "--save")
        self.assertEqual(saved["saved"], "PLAN_1")
        self.assertEqual(self.comp("forecast")["plan"]["key"], "PLAN_1")

    def test_review_adjusts_both_ways(self):
        self.mortgages()
        self.comp("plan", "--strategy", "avalanche", "--extra", "3000", "--save")
        self.comp("pay", "--credit", "credit:hipoteca-infonavit", "--amount", "6000", "--date", "2026-10-20")
        self.comp("pay", "--credit", "credit:hipoteca-bbva", "--amount", "20000", "--date", "2026-10-05")
        review = self.comp("review", "--month", "2026-10", today="2026-11-02")
        status = {p["credit"]: p["status"] for p in review["payments"]}
        self.assertEqual(status, {"Hipoteca BBVA": "above_plan", "Hipoteca Infonavit": "as_planned"})
        self.assertLessEqual(review["recalculated"][0]["months_later"], 0)

    def test_review_after_a_minimum_month_moves_the_dates(self):
        self.mortgages()
        self.comp("plan", "--strategy", "avalanche", "--extra", "3000", "--save")
        self.comp("pay", "--credit", "credit:hipoteca-bbva", "--amount", "12000", "--date", "2026-10-05")
        review = self.comp("review", "--month", "2026-10", today="2026-11-02")
        bbva = next(p for p in review["payments"] if p["credit"] == "Hipoteca BBVA")
        self.assertEqual(bbva["status"], "minimum_or_partial_extra")
        self.assertIn("parte del plan", review["note"])

    def test_review_without_a_plan_explains(self):
        self.mortgages()
        result = self.comp("review", "--month", "2026-10", ok=False)
        self.assertIn("plan", result["error"]["message"])


if __name__ == "__main__":
    unittest.main()
