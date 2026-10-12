"""Módulo compromisos de finanzas-personales: créditos, ingreso esperado, colchón, pronóstico y plan de liquidación.

Comandos (salida JSON en stdout):
  activate   activa el módulo: predicados y tipos en la memoria
  credit     registra o cambia un crédito (hipoteca, auto, préstamo...)
  balance    saldo real de un crédito a una fecha (el que da el acreedor)
  link       regla: los cargos de un comercio o tipo son pagos de un crédito
  pay        registra un pago a un crédito que dice la persona
  sync       crea los pagos pendientes de los créditos, liga cargos importados y cierra los cubiertos
  income     fuente de ingreso (moneda, monto, frecuencia; esperado o promedio)
  fx         tipo de cambio de referencia
  cushion    meta del colchón y cuentas donde vive
  forecast   presupuesto, real y pronóstico por horizonte; margen, colchón y lo que se libera
  plan       amortización con avalancha y bola de nieve; --save guarda la versión aprobada
  review     plan contra real de un mes y el plan recalculado desde lo real
  cascades   compromisos que se pagan con tarjeta y qué pasa si la tarjeta no se cubre

Solo biblioteca estándar. Montos: enteros en centavos (MXN_cent). Usa la memoria a través de fin.py.
"""

from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import os
import sys
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fin  # noqa: E402
from fin import BAD_INPUT, CATEGORY, LATEST, OK, FinError, Mem, at, cents, money, slug, source  # noqa: E402

__version__ = fin.__version__
MODULE = "module:compromisos"
HORIZONS = {"week": 0, "month": 1, "quarter": 3, "semester": 6, "year": 12}
FREQUENCY = {"monthly": Decimal(1), "biweekly": Decimal(26) / 12, "weekly": Decimal(52) / 12}
MAX_MONTHS = 600


# -- utilidades ---------------------------------------------------------------------
def day_of(value: Any) -> date:
    return date.fromisoformat(str(value)[:10])


def add_months(d: date, n: int, day: int | None = None) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    return date(y, m, min(day or d.day, calendar.monthrange(y, m)[1]))


def month_start(d: date) -> date:
    return d.replace(day=1)


def ym(d: date) -> str:
    return f"{d:%Y-%m}"


def interest(balance: int, rate_bp: int) -> int:
    """Interés de un mes sobre saldo insoluto: tasa anual / 12, redondeado al centavo."""
    return int((Decimal(balance) * rate_bp / 120000).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def decimal_text(text: str, what: str) -> Decimal:
    try:
        value = Decimal(str(text).replace(",", ""))
    except InvalidOperation as error:
        raise FinError(f"{what} debe ser un número: {text!r}.") from error
    if value <= 0:
        raise FinError(f"{what} debe ser mayor que cero.")
    return value


def today_of(args) -> date:
    return date.fromisoformat(args.today) if args.today else date.today()


def write(mem: Mem, args, content: str, kind: str = "user_statement", **doc) -> dict:
    return mem.write({"source": source(args.by, args.source or content, kind), "performed_by": args.by, **doc})


def all_rows(mem: Mem, *args: str) -> list[dict]:
    out, offset = [], 0
    while True:
        page = mem.run("list", *args, "--limit", "1000", "--offset", str(offset))
        out += page["rows"]
        if not page.get("truncated"):
            return out
        offset += len(page["rows"])


def require_active(mem: Mem) -> None:
    found = mem.rows("--entity-type", "module", "--where", f"key = {MODULE}", "--column", "key")
    rows = found and mem.rows("--entity-type", "module", "--where", f"key = {MODULE}", "--column", "fact:module_active")
    if not rows or rows[0].get("fact:module_active") is not True:
        raise FinError("El módulo compromisos no está activo. Actívalo con `activate` cuando la persona lo pida.")


# -- activación ------------------------------------------------------------------------
def cmd_activate(mem: Mem, args) -> dict:
    seed = fin.load_seed()["compromisos"]
    result = mem.write({"source": source(args.by, args.source or "activate compromisos", "user_statement"),
                        "performed_by": args.by,
                        "predicates": [{**p, "distinct_from_similar": True} for p in seed["predicates"]],
                        "entities": [{"key": MODULE, "type": "module", "name": "Compromisos",
                                      "aliases": ["Módulo compromisos"]}],
                        "facts": [{"subject": MODULE, "predicate": "module_active", "value": True,
                                   "valid_from": "now"}]})
    for pred, values in seed["allowed_values"].items():
        mem.run("define-values", "--predicate", pred, *[x for v in values for x in ("--value", v)], "--by", args.by)
    return {"ok": True, "module": "compromisos", "active": True, "warnings": fin.quiet(result.get("warnings", []))}


# -- créditos ------------------------------------------------------------------------------
def credits(mem: Mem) -> list[dict]:
    cols = ["key", "name", "fact:credit_kind", "fact:lender", "fact:annual_rate_bp", "fact:scheduled_payment",
            "fact:included_charges", "fact:payment_day", "fact:remaining_payments", "fact:principal_balance",
            "fact:principal_balance/since", "fact:paid_with/key", "fact:paid_with/fact:account_product",
            "fact:paid_with/name", "fact:prepayment_allowed", "fact:tracking_since"]
    rows = mem.rows("--entity-type", "credit", "--as-of", LATEST, *[x for c in cols for x in ("--column", c)])
    out = []
    for r in rows:
        out.append({"key": r["key"], "name": r["name"], "kind": r.get("fact:credit_kind"),
                    "lender": r.get("fact:lender"), "rate_bp": r.get("fact:annual_rate_bp"),
                    "payment": r.get("fact:scheduled_payment") or 0, "charges": r.get("fact:included_charges") or 0,
                    "day": r.get("fact:payment_day") or 1, "remaining": r.get("fact:remaining_payments"),
                    "balance": r.get("fact:principal_balance"),
                    "balance_since": day_of(r["fact:principal_balance/since"]) if r.get("fact:principal_balance/since") else None,
                    "paid_with": r.get("fact:paid_with/key"), "paid_with_name": r.get("fact:paid_with/name"),
                    "paid_with_product": r.get("fact:paid_with/fact:account_product"),
                    "prepayment": r.get("fact:prepayment_allowed") is not False,
                    "since": day_of(r["fact:tracking_since"]) if r.get("fact:tracking_since") else None})
    return out


def credit_by_key(mem: Mem, key: str) -> dict:
    for c in credits(mem):
        if c["key"] == key:
            return c
    raise FinError(f"No existe el crédito {key}. Regístralo con `credit`.")


def cmd_credit(mem: Mem, args) -> dict:
    require_active(mem)
    if not (args.key or args.name):
        raise FinError("Indica el crédito con --name (nuevo) o --key (existente).")
    key = args.key or f"credit:{slug(args.name)}"
    if not key.startswith("credit:"):
        raise FinError("La clave de un crédito empieza con credit:.")
    if args.rate is None and args.remaining is None and not args.update:
        raise FinError("Sin tasa, el crédito necesita --remaining (pagos que faltan) para llevar su calendario.")
    day = args.day
    if day is not None and not 1 <= day <= 31:
        raise FinError("--day debe estar entre 1 y 31.")
    facts = []
    def fact(pred, value, valid_from="now"):
        if value is not None:
            facts.append({"subject": key, "predicate": pred, "value": value, "valid_from": valid_from})
    fact("credit_kind", args.kind)
    fact("lender", args.lender)
    fact("annual_rate_bp", int((decimal_text(args.rate, "--rate") * 100).quantize(Decimal(1))) if args.rate else None)
    fact("scheduled_payment", cents(decimal_text(args.payment, "--payment")) if args.payment else None)
    fact("included_charges", cents(args.charges) if args.charges is not None else None)
    fact("payment_day", day)
    fact("remaining_payments", args.remaining)
    fact("paid_with", args.paid_with)
    fact("prepayment_allowed", {"yes": True, "no": False}.get(args.prepayment) if args.prepayment else None)
    if args.balance:
        fact("principal_balance", cents(decimal_text(args.balance, "--balance")),
             at(args.balance_date or today_of(args).isoformat(), args.tz))
    entities = []
    if not args.update:
        if not (args.name and args.payment and day):
            raise FinError("Un crédito nuevo necesita --name, --payment y --day.")
        entities.append({"key": key, "type": "credit", "name": args.name})
        fact("tracking_since", at((args.since or today_of(args).replace(day=1).isoformat()), args.tz))
    result = write(mem, args, f"credit {key}", entities=entities, facts=facts)
    c = credit_by_key(mem, key)
    out = {"ok": True, "credit": key, "name": c["name"], "rate_pct": pct(c["rate_bp"]), "payment": money(c["payment"]),
           "day": c["day"], "balance": money(c["balance"]), "paid_with": c["paid_with_name"],
           "warnings": fin.quiet(result.get("warnings", []))}
    if c["rate_bp"] and c["balance"] and c["payment"] - c["charges"] <= interest(c["balance"], c["rate_bp"]):
        out["warnings"].append("El pago menos los cargos incluidos no cubre el interés del mes: revisa los datos.")
    return out


def pct(bp: int | None) -> str | None:
    return None if bp is None else f"{Decimal(bp) / 100:.2f} %"


def cmd_balance(mem: Mem, args) -> dict:
    require_active(mem)
    credit_by_key(mem, args.credit)
    day = args.date or today_of(args).isoformat()
    value = cents(decimal_text(args.amount, "--amount"))
    result = write(mem, args, f"balance {args.credit} {args.amount} at {day}",
                   facts=[{"subject": args.credit, "predicate": "principal_balance", "value": value,
                           "valid_from": at(day, args.tz)}])
    return {"ok": True, "credit": args.credit, "balance": money(value), "date": day,
            "warnings": fin.quiet(result.get("warnings", []))}


def cmd_link(mem: Mem, args) -> dict:
    require_active(mem)
    credit_by_key(mem, args.credit)
    if not args.classifier.split(":")[0] in ("merchant", "counterparty", "kind"):
        raise FinError("--classifier debe ser merchant:…, counterparty:… o kind:…")
    result = write(mem, args, f"{args.classifier} pays {args.credit}",
                   facts=[{"subject": args.classifier, "predicate": "pays_credit", "value": args.credit,
                           "valid_from": "now"}])
    synced = sync(mem, args, today_of(args))
    return {"ok": True, "classifier": args.classifier, "credit": args.credit, "sync": synced,
            "warnings": fin.quiet(result.get("warnings", []))}


def cmd_pay(mem: Mem, args) -> dict:
    require_active(mem)
    credit_by_key(mem, args.credit)
    amount = cents(decimal_text(args.amount, "--amount"))
    day = args.date or today_of(args).isoformat()
    key = "CPAY_" + hashlib.sha256(f"{args.credit}|{day}|{amount}|{args.nonce or ''}".encode()).hexdigest()[:16]
    result = write(mem, args, f"payment {args.credit} {args.amount} {day}", events=[{
        "key": key, "type": "credit_payment", "occurred_at": at(day, args.tz),
        "summary": f"Paid {money(amount)} to {args.credit}",
        "attributes": {"credit_payment_amount": amount, "entry_source": "manual"},
        "links": [{"predicate": "for_credit", "entity": args.credit}]}])
    return {"ok": True, "key": key, "credit": args.credit, "amount": money(amount), "date": day,
            "created": bool(result.get("events", {}).get("created")), "sync": sync(mem, args, today_of(args))}


# -- pagos pendientes y su cierre ---------------------------------------------------------------
def due_dates(c: dict, until: date) -> list[date]:
    """Fechas de pago desde que se lleva el crédito hasta el primer pago en o después de `until`."""
    start = c["since"] or month_start(until)
    d = add_months(month_start(start), 0, c["day"])
    if d < start:
        d = add_months(month_start(start), 1, c["day"])
    out = []
    while True:
        out.append(d)
        if d >= until or len(out) > MAX_MONTHS:
            return out
        d = add_months(month_start(d), 1, c["day"])


def payments(mem: Mem, credit: str) -> list[tuple[date, int]]:
    rows = all_rows(mem, "--event-type", "credit_payment", "--where", f"link:for_credit = {credit}",
                    "--column", "occurred_at", "--column", "attr:credit_payment_amount")
    return sorted((day_of(r["occurred_at"]), r["attr:credit_payment_amount"]) for r in rows)


def statement_through(mem: Mem, account: str | None) -> date | None:
    if not account:
        return None
    rows = mem.rows("--event-type", "statement_imported", "--where", f"link:on_account = {account}",
                    "--column", "attr:period_end")
    ends = [day_of(r["attr:period_end"]) for r in rows if r.get("attr:period_end")]
    return max(ends) if ends else None


def verified_through(mem: Mem, c: dict) -> date | None:
    """Hasta qué fecha se pueden ver los pagos de un crédito en los estados importados.

    Sin una regla que ligue sus cargos (`link`) solo cuentan los pagos que dice la persona: nada se da por no pagado.
    """
    for etype in ("merchant", "counterparty", "tx_kind"):
        if mem.rows("--entity-type", etype, "--where", f"fact:pays_credit = {c['key']}", "--column", "key"):
            return statement_through(mem, c["paid_with"])
    return None


def sync(mem: Mem, args, today: date) -> dict:
    """Liga los cargos a los créditos, crea los pagos pendientes y cierra los que ya se pueden verificar."""
    report = {"linked_payments": 0, "dues_created": [], "dues_settled": [], "overdue_unverified": []}
    for c in credits(mem):
        rows = all_rows(mem, "--event-type", "transaction", "--where",
                        f"link:classified_by/fact:pays_credit = {c['key']}", "--where", "no:link-in:from_transaction",
                        "--column", "key", "--column", "occurred_at", "--column", "attr:amount")
        events = [{"key": f"CPAY_{r['key']}", "type": "credit_payment", "occurred_at": r["occurred_at"],
                   "summary": f"Paid {money(abs(r['attr:amount']))} to {c['key']} (from {r['key']})",
                   "attributes": {"credit_payment_amount": abs(r["attr:amount"]), "entry_source": "statement"},
                   "links": [{"predicate": "for_credit", "entity": c["key"]},
                             {"predicate": "from_transaction", "event": r["key"]}]}
                  for r in rows if r["attr:amount"] < 0]
        if events:
            mem.write({"source": source(args.by, f"payments of {c['key']} found in statements", "import"),
                       "performed_by": args.by, "events": events})
            report["linked_payments"] += len(events)

        existing = {r["key"] for r in mem.rows("--event-type", "payment_due", "--where", f"link:for_credit = {c['key']}",
                                               "--column", "key")}
        settlements = {r["link:resolves/key"]: r for r in mem.rows(
            "--event-type", "credit_due_settled", "--where", f"link:for_credit = {c['key']}",
            "--column", "key", "--column", "link:resolves/key", "--column", "attr:paid_amount")}
        versions: dict[str, int] = {}
        for r in mem.rows("--event-type", "credit_due_settled", "--where", f"link:for_credit = {c['key']}",
                          "--include-voided", "--column", "link:resolves/key"):
            versions[r["link:resolves/key"]] = versions.get(r["link:resolves/key"], 0) + 1
        paid = payments(mem, c["key"])
        through = verified_through(mem, c)
        arrears, previous, new_events, void = 0, None, [], []
        for d in due_dates(c, today):
            key = f"DUE_{c['key'].split(':', 1)[1]}_{ym(d)}"
            if key not in existing:
                new_events.append({
                    "key": key, "type": "payment_due", "occurred_at": at(add_months(d, -1).isoformat(), args.tz),
                    "summary": f"Pay {money(c['payment'])} on {c['name']} by {d}",
                    "attributes": {"payment_due_date": at(d.isoformat(), args.tz), "scheduled_payment": c["payment"],
                                   "requested_action": f"Pay {money(c['payment'])} on {c['name']} by {d}"},
                    "pending_for": args.by, "links": [{"predicate": "for_credit", "entity": c["key"]}]})
                report["dues_created"].append(key)
            window = sum(a for p, a in paid if (previous is None or p > previous) and p <= d)
            to_arrears = min(window, arrears)
            rest = window - to_arrears
            covered = rest >= c["payment"]
            settled = settlements.get(key)
            if settled and settled["attr:paid_amount"] != window:
                # llegó un pago después del cierre (importación tardía o dicho por la persona): se rehace
                void.append({"event": settled["key"], "reason": "Payments of the period changed; settled again"})
                settled = None
            verifiable = through is not None and through >= d
            if not settled and (covered or (d < today and verifiable)):
                shortfall = max(0, c["payment"] - rest)
                n = versions[key] = versions.get(key, 0) + 1
                new_events.append({
                    "key": f"PAID_{key}" + (f"_{n}" if n > 1 else ""), "type": "credit_due_settled",
                    "occurred_at": at(d.isoformat(), args.tz),
                    "summary": f"Paid {money(window)} of {money(c['payment'])} on {c['name']} by {d}",
                    "attributes": {"paid_amount": window, "shortfall": shortfall, "covered": covered,
                                   "extra_payment": max(0, rest - c["payment"]), "arrears_paid": to_arrears},
                    "links": [{"predicate": "resolves", "event": key}, {"predicate": "for_credit", "entity": c["key"]}]})
                report["dues_settled"].append({"due": key, "paid": money(window), "covered": covered,
                                               "shortfall": money(shortfall),
                                               "extra": money(max(0, rest - c["payment"])),
                                               "arrears_paid": money(to_arrears)})
            elif not settled and d < today:
                report["overdue_unverified"].append({"due": key, "credit": c["name"], "due_date": d.isoformat(),
                                                     "paid_so_far": money(window),
                                                     "statement_through": through.isoformat() if through else None})
            arrears = arrears - to_arrears + max(0, c["payment"] - rest)
            previous = d
        if new_events or void:
            mem.write({"source": source(args.by, f"payment schedule of {c['key']}", "helper_command"),
                       "performed_by": args.by, "events": new_events, **({"void": void} if void else {})})
    return report


def cmd_sync(mem: Mem, args) -> dict:
    require_active(mem)
    return {"ok": True, **sync(mem, args, today_of(args)), "pending": mem.run("pending")}


# -- ingreso, tipo de cambio y colchón ---------------------------------------------------------------
def cmd_income(mem: Mem, args) -> dict:
    require_active(mem)
    key = args.key or f"income:{slug(args.name)}"
    if args.mode == "expected" and not args.amount:
        raise FinError("Un ingreso esperado necesita --amount.")
    currency = args.currency.upper()
    facts = [{"subject": key, "predicate": "income_currency", "value": currency, "valid_from": "now"},
             {"subject": key, "predicate": "income_frequency", "value": args.frequency, "valid_from": "now"},
             {"subject": key, "predicate": "income_mode", "value": args.mode, "valid_from": "now"}]
    if args.amount:
        facts.append({"subject": key, "predicate": "income_amount", "value": cents(decimal_text(args.amount, "--amount")),
                      "valid_from": "now"})
    if args.mode == "average":
        facts.append({"subject": key, "predicate": "average_months", "value": args.months, "valid_from": "now"})
    result = write(mem, args, f"income {key}", entities=[{"key": key, "type": "income_source", "name": args.name}],
                   facts=facts)
    return {"ok": True, "income": key, "currency": currency, "mode": args.mode, "frequency": args.frequency,
            "warnings": fin.quiet(result.get("warnings", []))}


def cmd_fx(mem: Mem, args) -> dict:
    require_active(mem)
    rate = decimal_text(args.rate, "--rate")
    key = f"currency:{args.currency.lower()}"
    result = write(mem, args, f"fx {args.currency} {rate}",
                   entities=[{"key": key, "type": "currency", "name": args.currency.upper()}],
                   facts=[{"subject": key, "predicate": "fx_rate_text", "value": str(rate), "valid_from": "now"}])
    return {"ok": True, "currency": args.currency.upper(), "mxn_per_unit": str(rate),
            "warnings": fin.quiet(result.get("warnings", []))}


def cmd_cushion(mem: Mem, args) -> dict:
    require_active(mem)
    facts = [{"subject": "cushion:main", "predicate": "cushion_target", "value": cents(decimal_text(args.target, "--target")),
              "valid_from": "now"}]
    current = cushion(mem)
    close = [{"subject": "cushion:main", "predicate": "held_in", "at": "now"}] \
        if args.account and current and current["accounts"] else []
    facts += [{"subject": "cushion:main", "predicate": "held_in", "value": a} for a in args.account or []]
    result = write(mem, args, f"cushion {args.target}", close=close,
                   entities=[{"key": "cushion:main", "type": "cushion", "name": "Colchón"}], facts=facts)
    return {"ok": True, "cushion": cushion(mem), "warnings": fin.quiet(result.get("warnings", []))}


def cushion(mem: Mem) -> dict | None:
    rows = mem.rows("--entity-type", "cushion", "--where", "key = cushion:main", "--as-of", LATEST,
                    "--column", "fact:cushion_target", "--column", "fact:held_in/key", "--column", "fact:held_in/name",
                    "--column", "fact:held_in/fact:balance")
    if not rows or rows[0].get("fact:cushion_target") is None:
        return None
    r = rows[0]
    as_list = lambda v: v if isinstance(v, list) else ([] if v is None else [v])  # noqa: E731
    balances = [b for b in as_list(r.get("fact:held_in/fact:balance")) if isinstance(b, int)]
    current = sum(balances)
    target = r["fact:cushion_target"]
    return {"target_cents": target, "current_cents": current, "gap_cents": max(0, target - current),
            "target": money(target), "current": money(current), "gap": money(max(0, target - current)),
            "accounts": as_list(r.get("fact:held_in/name"))}


# -- pronóstico -----------------------------------------------------------------------------------
def spending_rows(mem: Mem, since: date, until: date) -> list[dict]:
    """Gasto que cuenta para el ritmo: sin internos, ingresos, pagos de crédito ni parcialidades a meses."""
    rows = all_rows(mem, "--event-type", "transaction", "--since", since.isoformat(), "--until", until.isoformat(),
                    "--column", "occurred_at", "--column", "attr:amount", "--column", f"{CATEGORY}/fact:part_of/key",
                    "--column", "link:classified_by/fact:pays_credit/key", "--column", "attr:installment_number")
    out = []
    for r in rows:
        top = r.get(f"{CATEGORY}/fact:part_of/key")
        if top in ("category:internal", "category:income") or r.get("link:classified_by/fact:pays_credit/key") \
                or r.get("attr:installment_number") is not None or (r.get("attr:amount") or 0) >= 0:
            continue
        out.append({"day": day_of(r["occurred_at"]), "amount": -r["attr:amount"], "uncategorized": top is None})
    return out


def data_through(mem: Mem) -> date | None:
    rows = mem.rows("--event-type", "statement_imported", "--column", "attr:period_end",
                    "--order-by", "desc:attr:period_end")
    return day_of(rows[0]["attr:period_end"]) if rows and rows[0].get("attr:period_end") else None


def pace(mem: Mem, today: date, days: int) -> dict:
    """Gasto promedio por día de los últimos `days` días con datos (el ADR de una persona)."""
    end = min(today, data_through(mem) or today)
    rows = spending_rows(mem, end - timedelta(days=days - 1), end + timedelta(days=1))
    first = min((r["day"] for r in rows), default=end)
    used = max(1, (end - max(first, end - timedelta(days=days - 1))).days + 1)
    total = sum(r["amount"] for r in rows)
    return {"daily_cents": round(total / used), "days_used": used, "data_through": end,
            "uncategorized_cents": sum(r["amount"] for r in rows if r["uncategorized"])}


def fx_rates(mem: Mem, override: str | None) -> dict[str, Decimal]:
    rates = {"MXN": Decimal(1)}
    for r in mem.rows("--entity-type", "currency", "--as-of", LATEST, "--column", "name", "--column", "fact:fx_rate_text"):
        if r.get("fact:fx_rate_text"):
            rates[r["name"].upper()] = Decimal(r["fact:fx_rate_text"])
    if override:
        cur, _, rate = override.partition("=")
        rates[cur.upper()] = decimal_text(rate, "--fx")
    return rates


def monthly_income(mem: Mem, today: date, rates: dict[str, Decimal]) -> tuple[int, list[dict], list[str]]:
    rows = mem.rows("--entity-type", "income_source", "--as-of", LATEST, "--column", "key", "--column", "name",
                    "--column", "fact:income_amount", "--column", "fact:income_currency",
                    "--column", "fact:income_frequency", "--column", "fact:income_mode", "--column", "fact:average_months")
    total, lines, warnings = 0, [], []
    for r in rows:
        if r.get("fact:income_mode") == "average":
            n = r.get("fact:average_months") or 6
            start = add_months(month_start(today), -n)
            got = mem.run("aggregate", "--event-type", "transaction", "--measure", "sum:amount", "--since",
                          start.isoformat(), "--until", month_start(today).isoformat(),
                          "--where", f"{CATEGORY}/fact:part_of = category:income")["groups"]
            value = round((got[0]["value"] or 0) / n) if got else 0
            lines.append({"source": r["name"], "mode": "average", "months": n, "monthly": money(value)})
        else:
            cur = r.get("fact:income_currency") or "MXN"
            if cur not in rates:
                warnings.append(f"Falta el tipo de cambio de {cur} para {r['name']}: usa `fx`.")
                continue
            factor = FREQUENCY.get(r.get("fact:income_frequency") or "monthly", Decimal(1))
            value = int((Decimal(r["fact:income_amount"]) * factor * rates[cur]).quantize(Decimal(1), rounding=ROUND_HALF_UP))
            lines.append({"source": r["name"], "mode": "expected", "currency": cur,
                          "fx": str(rates[cur]) if cur != "MXN" else None, "monthly": money(value)})
        total += value
    if not rows:
        warnings.append("No hay fuentes de ingreso registradas: el margen no incluye ingresos (usa `income`).")
    return total, lines, warnings


def budget_total(mem: Mem, as_of: date) -> int | None:
    rows = mem.rows("--entity-type", "category", "--where", "has:fact:monthly_budget", "--as-of", as_of.isoformat(),
                    "--column", "key", "--column", "fact:monthly_budget")
    values = [r["fact:monthly_budget"] for r in rows
              if r["key"].split("/")[0] not in ("category:income", "category:internal")]
    return sum(values) if values else None


def installment_plans(mem: Mem) -> list[dict]:
    rows = mem.rows("--entity-type", "installment_plan", "--as-of", LATEST, "--where", "fact:pending_balance > 0",
                    "--column", "name", "--column", "fact:pending_balance", "--column", "fact:plan_original_amount",
                    "--column", "fact:installments_total", "--column", "fact:installments_paid",
                    "--column", "fact:installments_paid/since", "--column", "fact:on_account/key")
    out = []
    for r in rows:
        total, paid = r.get("fact:installments_total"), r.get("fact:installments_paid") or 0
        if not total or not r.get("fact:plan_original_amount"):
            continue
        left = max(1, total - paid)
        out.append({"name": r["name"], "card": r.get("fact:on_account/key"),
                    "monthly_cents": min(r["fact:pending_balance"], round(r["fact:plan_original_amount"] / total)),
                    "pending_cents": r["fact:pending_balance"], "left": left,
                    "last_month": add_months(day_of(r["fact:installments_paid/since"]) if r.get("fact:installments_paid/since")
                                             else date.today(), left)})
    return out


def msi_for(plans: list[dict], month: date) -> int:
    return sum(p["monthly_cents"] for p in plans if month_start(month) <= month_start(p["last_month"]))


def latest_plan(mem: Mem, until: date | None = None) -> dict | None:
    args = ["--event-type", "debt_plan", "--column", "key", "--column", "occurred_at", "--column", "attr:strategy",
            "--column", "attr:extra_monthly", "--column", "attr:plan_detail_text", "--order-by", "desc:occurred_at"]
    if until:
        args += ["--until", until.isoformat()]
    rows = mem.rows(*args)
    if not rows:
        return None
    r = rows[0]
    return {"key": r["key"], "saved": str(r["occurred_at"])[:10], "strategy": r["attr:strategy"],
            "extra_cents": r["attr:extra_monthly"], "detail": json.loads(r["attr:plan_detail_text"])}


def cmd_forecast(mem: Mem, args) -> dict:
    require_active(mem)
    today = today_of(args)
    sync(mem, args, today)
    rates = fx_rates(mem, args.fx)
    p = pace(mem, today, args.pace_days)
    daily = p["daily_cents"]
    income, income_lines, warnings = monthly_income(mem, today, rates)
    cs = credits(mem)
    plans = installment_plans(mem)
    plan = latest_plan(mem)
    extra = plan["extra_cents"] if plan else 0
    cush = cushion(mem)
    sim = simulate(start_balances(mem, cs, today), today, extra, plan["strategy"] if plan else "avalanche") if cs else None
    out: dict[str, Any] = {"ok": True, "horizon": args.horizon, "today": today.isoformat(),
                           "data_through": p["data_through"].isoformat(),
                           "pace": {"daily": money(daily), "days_used": p["days_used"],
                                    "uncategorized_in_pace": money(p["uncategorized_cents"])},
                           "income_monthly": money(income), "income_sources": income_lines,
                           "plan": {"key": plan["key"], "strategy": plan["strategy"], "extra": money(extra)} if plan else None,
                           "cushion": cush, "cascades": cascades(mem, cs, plans)}
    if p["data_through"] < today:
        warnings.append(f"Hay movimientos importados hasta {p['data_through']}; lo posterior se estima con el ritmo.")
    if args.horizon == "week":
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        actual = sum(r["amount"] for r in spending_rows(mem, start, min(end, p["data_through"]) + timedelta(days=1)))
        rest = max(0, (end - max(p["data_through"], start - timedelta(days=1))).days)
        b = budget_total(mem, today)
        forecast = actual + daily * rest
        out.update({"week": [start.isoformat(), end.isoformat()], "actual": money(actual), "forecast": money(forecast),
                    "budget": money(round(b * 7 / calendar.monthrange(today.year, today.month)[1])) if b else None,
                    "variance": money(round(b * 7 / calendar.monthrange(today.year, today.month)[1]) - forecast) if b else None,
                    "dues_this_week": dues_between(mem, start, end)})
    else:
        months = []
        cumulative = 0
        for i in range(HORIZONS[args.horizon]):
            m = add_months(month_start(today), i)
            days = calendar.monthrange(m.year, m.month)[1]
            b = budget_total(mem, add_months(m, 1) - timedelta(days=1))
            if i == 0:
                last = min(p["data_through"], add_months(m, 1) - timedelta(days=1))
                actual = sum(r["amount"] for r in spending_rows(mem, m, last + timedelta(days=1))) if last >= m else 0
                rest = (add_months(m, 1) - max(last + timedelta(days=1), m)).days
                spend = actual + daily * rest
            else:
                actual, spend = None, daily * days
            minimums = sum(sim["by_month"].get(ym(m), {}).get(c["key"], {}).get("required", 0) for c in cs) if sim else 0
            if i == 0 and sim:
                # el pago de este mes que ya pasó no está en el ritmo ni en la simulación, pero sí sale del mes
                minimums += sum(c["payment"] for c in cs if c["day"] <= today.day and c["key"] in sim["payoff"]
                                and (sim["payoff"][c["key"]] or "9999") >= ym(m))
            planned_extra = sum(sim["by_month"].get(ym(m), {}).get(c["key"], {}).get("extra", 0) for c in cs) if sim else 0
            msi = msi_for(plans, m)
            margin = income - spend - minimums - msi
            cumulative += margin - planned_extra
            months.append({"month": ym(m), "income": money(income), "budget": money(b), "actual_to_date": money(actual),
                           "spending_forecast": money(spend), "variance_vs_budget": money(b - spend) if b else None,
                           "credit_payments": money(minimums), "installments": money(msi), "margin": money(margin),
                           "planned_extra": money(planned_extra), "margin_after_plan": money(margin - planned_extra),
                           "cumulative": money(cumulative), "_margin": margin})
        gap = cush["gap_cents"] if cush else 0
        first = months[0]["_margin"]
        out["available_for_extra"] = money(max(0, first - gap))
        out["available_note"] = ("Propuesta: margen del mes menos lo que falta del colchón. La persona decide; "
                                 "puede ser $0.")
        for row in months:
            row.pop("_margin")
        out["months"] = months
        horizon_end = add_months(month_start(today), HORIZONS[args.horizon])
        out["msi_ending"] = [{"name": pl["name"], "last_month": ym(pl["last_month"]), "frees_monthly": money(pl["monthly_cents"])}
                             for pl in plans if month_start(pl["last_month"]) < horizon_end]
        if sim:
            out["credits_ending"] = [{"credit": k, "payoff": v} for k, v in sim["payoff"].items()
                                     if v and v < ym(horizon_end)]
    out["warnings"] = warnings
    return out


def dues_between(mem: Mem, start: date, end: date) -> list[dict]:
    rows = mem.rows("--event-type", "payment_due", "--where", "no:link-in:resolves",
                    "--where", f"attr:payment_due_date between {start}..{end + timedelta(days=1)}",
                    "--column", "summary", "--column", "attr:payment_due_date")
    return [{"summary": r["summary"], "due_date": str(r["attr:payment_due_date"])[:10]} for r in rows]


# -- cascadas ---------------------------------------------------------------------------------------
def cascades(mem: Mem, cs: list[dict], plans: list[dict]) -> list[dict]:
    """Compromisos que se cargan a una tarjeta: si la tarjeta no se cubre completa, pasan a la tasa de la tarjeta."""
    cards: dict[str, dict] = {}
    for c in cs:
        if c["paid_with_product"] == "credit":
            card = cards.setdefault(c["paid_with"], {"card": c["paid_with_name"], "commitments": [], "_key": c["paid_with"]})
            card["commitments"].append({"credit": c["name"], "monthly": money(c["payment"]), "_c": c["payment"]})
    out = []
    for key, card in cards.items():
        msi = sum(pl["monthly_cents"] for pl in plans if pl["card"] == key)
        last = mem.rows("--event-type", "payment_due_settled", "--where", f"link:on_account = {key}",
                        "--column", "occurred_at", "--column", "attr:covered", "--column", "attr:shortfall",
                        "--order-by", "desc:occurred_at", "--limit", "1")
        st = mem.rows("--event-type", "statement_imported", "--where", f"link:on_account = {key}",
                      "--column", "attr:interest_charged", "--column", "attr:period_end", "--order-by", "desc:attr:period_end")
        on_card = sum(x.pop("_c") for x in card["commitments"])
        entry = {"card": card["card"], "commitments": card["commitments"], "installments_monthly": money(msi),
                 "on_card_monthly": money(on_card + msi),
                 "last_card_payment": {"date": str(last[0]["occurred_at"])[:10], "covered": last[0]["attr:covered"],
                                       "shortfall": money(last[0]["attr:shortfall"])} if last else None,
                 "interest_last_statement": money(st[0].get("attr:interest_charged")) if st else None,
                 "note": ("Estos pagos cuentan dentro del pago para no generar intereses de la tarjeta. "
                          "Si la tarjeta no se cubre completa, la parte no pagada genera intereses a la tasa de la tarjeta.")}
        entry["at_risk"] = bool(last and not last[0]["attr:covered"])
        out.append(entry)
    return out


def cmd_cascades(mem: Mem, args) -> dict:
    require_active(mem)
    sync(mem, args, today_of(args))
    return {"ok": True, "cascades": cascades(mem, credits(mem), installment_plans(mem))}


# -- plan de liquidación ------------------------------------------------------------------------------
def estimate_balance(mem: Mem, c: dict, today: date) -> tuple[int | None, bool]:
    """Saldo estimado hoy: el último saldo real más los pagos registrados después, mes por mes."""
    if c["balance"] is None or not c["rate_bp"]:
        return c["balance"], False
    bal, since = c["balance"], c["balance_since"]
    paid = [(d, a) for d, a in payments(mem, c["key"]) if d > since]
    through = verified_through(mem, c)
    estimated = False
    d = add_months(month_start(since), 0, c["day"])
    if d <= since:
        d = add_months(month_start(since), 1, c["day"])
    prev = since
    while d <= today and bal > 0:
        window = sum(a for p, a in paid if prev < p <= d)
        if not window and not (through and through >= d):
            window = c["payment"]  # aún no se puede ver: se supone el pago exigible
        bal = max(0, bal + interest(bal, c["rate_bp"]) - max(0, window - (c["charges"] if window else 0)))
        estimated, prev = True, d
        d = add_months(month_start(d), 1, c["day"])
    return bal, estimated


def start_balances(mem: Mem, cs: list[dict], today: date) -> list[dict]:
    out = []
    for c in cs:
        bal, est = estimate_balance(mem, c, today)
        out.append({**c, "start": bal, "estimated": est})
    return out


def simulate(cs: list[dict], today: date, extra: int, strategy: str) -> dict:
    """Mes a mes: interés, pago exigible y el extra (más los pagos que se liberan) al crédito objetivo."""
    state = {}
    for c in cs:
        if c["rate_bp"] and c["start"]:
            state[c["key"]] = {"bal": c["start"], "c": c, "interest": 0, "payoff": None, "fixed": False}
        elif c["remaining"]:
            state[c["key"]] = {"left": c["remaining"], "c": c, "interest": None, "payoff": None, "fixed": True}
    by_month: dict[str, dict] = {}
    month = month_start(today)
    for _ in range(MAX_MONTHS):
        active = [k for k, s in state.items() if s["payoff"] is None]
        if not active:
            break
        freed = sum(s["c"]["payment"] for s in state.values() if s["payoff"] is not None)
        pool = extra + (freed if extra else 0)
        row = by_month.setdefault(ym(month), {})
        for k in active:
            s = state[k]
            if month == month_start(today) and s["c"]["day"] <= today.day and not s["fixed"]:
                continue  # el pago de este mes ya pasó: está en el saldo de partida
            if s["fixed"]:
                row[k] = {"required": s["c"]["payment"], "extra": 0, "balance": None}
                s["left"] -= 1
                if s["left"] <= 0:
                    s["payoff"] = ym(month)
                continue
            i = interest(s["bal"], s["c"]["rate_bp"])
            principal = s["c"]["payment"] - s["c"]["charges"] - i
            if principal <= 0:
                raise FinError(f"El pago de {s['c']['name']} no cubre sus intereses: revisa tasa, pago y saldo.")
            required = min(s["c"]["payment"], s["bal"] + i + s["c"]["charges"])
            s["bal"] = max(0, s["bal"] + i + s["c"]["charges"] - required)
            s["interest"] += i
            row[k] = {"required": required, "extra": 0, "balance": s["bal"]}
        targets = [k for k in active if not state[k]["fixed"] and state[k]["bal"] > 0 and state[k]["c"]["prepayment"]]
        if strategy == "avalanche":
            targets.sort(key=lambda k: (-state[k]["c"]["rate_bp"], state[k]["bal"]))
        else:
            targets.sort(key=lambda k: (state[k]["bal"], -state[k]["c"]["rate_bp"]))
        for k in targets:
            if k not in row:
                row[k] = {"required": 0, "extra": 0, "balance": state[k]["bal"]}
            if pool <= 0:
                break
            put = min(pool, state[k]["bal"])
            state[k]["bal"] -= put
            row[k]["extra"] += put
            row[k]["balance"] = state[k]["bal"]
            pool -= put
        for k in active:
            if not state[k]["fixed"] and state[k]["bal"] <= 0:
                state[k]["payoff"] = ym(month)
        month = add_months(month, 1)
    return {"payoff": {k: s["payoff"] for k, s in state.items()},
            "interest": {k: s["interest"] for k, s in state.items()}, "by_month": by_month,
            "debt_free": max((s["payoff"] for s in state.values() if s["payoff"]), default=None),
            "not_simulated": [c["name"] for c in cs if c["key"] not in state]}


def months_between(a: str | None, b: str | None) -> int | None:
    if not a or not b:
        return None
    (ya, ma), (yb, mb) = map(int, a.split("-")), map(int, b.split("-"))
    return (yb - ya) * 12 + (mb - ma)


def summarize(sim: dict, base: dict, cs: list[dict]) -> dict:
    names = {c["key"]: c["name"] for c in cs}
    total = sum(v for v in sim["interest"].values() if v is not None)
    base_total = sum(v for v in base["interest"].values() if v is not None)
    return {"debt_free": sim["debt_free"], "total_interest": money(total), "interest_saved": money(base_total - total),
            "months_saved": months_between(sim["debt_free"], base["debt_free"]),
            "credits": [{"credit": names[k], "payoff": v,
                         "interest": money(sim["interest"][k]) if sim["interest"][k] is not None else None,
                         "months_earlier": months_between(v, base["payoff"][k])} for k, v in sim["payoff"].items()]}


def cmd_plan(mem: Mem, args) -> dict:
    require_active(mem)
    today = today_of(args)
    sync(mem, args, today)
    cs = start_balances(mem, credits(mem), today)
    if not cs:
        raise FinError("No hay créditos registrados.")
    extra = cents(args.extra) if args.extra is not None else 0
    if extra < 0:
        raise FinError("--extra no puede ser negativo.")
    base = simulate(cs, today, 0, "avalanche")
    strategies = [args.strategy] if args.strategy else ["avalanche", "snowball"]
    sims = {s: simulate(cs, today, extra, s) for s in strategies}
    out: dict[str, Any] = {
        "ok": True, "today": today.isoformat(), "extra_monthly": money(extra),
        "starting_balances": [{"credit": c["name"], "balance": money(c["start"]), "estimated": c["estimated"],
                               "rate": pct(c["rate_bp"])} for c in cs],
        "minimum_only": {"debt_free": base["debt_free"], "total_interest": money(sum(
            v for v in base["interest"].values() if v is not None))},
        "strategies": {s: summarize(sim, base, cs) for s, sim in sims.items()},
        "not_simulated": base["not_simulated"],
        "note": "Estimación con tasa anual / 12 sobre saldo insoluto; el saldo oficial es el del acreedor."}
    if args.save:
        if len(strategies) != 1:
            raise FinError("Para guardar el plan elige una estrategia con --strategy.")
        sim = sims[strategies[0]]
        detail = {"payoff": sim["payoff"], "debt_free": sim["debt_free"],
                  "months": {m: {k: {"required": v["required"], "extra": v["extra"]} for k, v in row.items()}
                             for m, row in list(sim["by_month"].items())[:24]}}
        n = len(mem.rows("--event-type", "debt_plan", "--column", "key")) + 1
        key = f"PLAN_{n}"
        write(mem, args, f"debt plan {strategies[0]} extra {args.extra}", events=[{
            "key": key, "type": "debt_plan", "occurred_at": at(today.isoformat(), args.tz),
            "summary": f"Plan {strategies[0]}, extra {money(extra)}/month, debt free {sim['debt_free']}",
            "attributes": {"strategy": strategies[0], "extra_monthly": extra,
                           "plan_detail_text": json.dumps(detail, separators=(",", ":"))},
            "links": [{"predicate": "covers_credit", "entity": c["key"]} for c in cs]}])
        out["saved"] = key
    return out


def cmd_review(mem: Mem, args) -> dict:
    require_active(mem)
    today = today_of(args)
    sync(mem, args, today)
    m = datetime.strptime(args.month, "%Y-%m").date()
    end = add_months(m, 1)
    plan = latest_plan(mem, end)
    if not plan:
        raise FinError("No hay un plan guardado antes de ese mes. Propón uno con `plan` y guárdalo con --save.")
    cs = credits(mem)
    planned_month = plan["detail"]["months"].get(args.month, {})
    lines = []
    for c in cs:
        planned = dict(planned_month.get(c["key"], {"extra": 0}))
        planned["required"] = planned.get("required") or c["payment"]  # el plan empezó después del pago del mes
        actual = sum(a for d, a in payments(mem, c["key"]) if m <= d < end)
        target = planned["required"] + planned["extra"]
        if actual == 0:
            status = "no_payment_found"
        elif actual < planned["required"]:
            status = "below_minimum"
        elif actual < target:
            status = "minimum_or_partial_extra"
        elif actual == target:
            status = "as_planned"
        else:
            status = "above_plan"
        lines.append({"credit": c["name"], "planned_minimum": money(planned["required"]),
                      "planned_extra": money(planned["extra"]), "paid": money(actual),
                      "difference": money(actual - target), "status": status})
    cs_now = start_balances(mem, cs, today)
    new = simulate(cs_now, today, plan["extra_cents"], plan["strategy"])
    names = {c["key"]: c["name"] for c in cs}
    shifts = [{"credit": names.get(k, k), "planned_payoff": v, "new_payoff": new["payoff"].get(k),
               "months_later": months_between(v, new["payoff"].get(k))} for k, v in plan["detail"]["payoff"].items()]
    return {"ok": True, "month": args.month, "plan": plan["key"], "strategy": plan["strategy"],
            "extra_monthly": money(plan["extra_cents"]), "payments": lines, "recalculated": shifts,
            "debt_free": {"planned": plan["detail"]["debt_free"], "now": new["debt_free"]},
            "note": "Recalculado desde el último saldo real y los pagos registrados. Un mes de mínimo es parte del plan."}


# -- CLI --------------------------------------------------------------------------------------------
def main() -> None:
    p = argparse.ArgumentParser(prog="compromisos.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"compromisos.py {__version__}")
    p.add_argument("--mem", help="Ruta a memory.py (por omisión, el skill project-memory instalado)")
    p.add_argument("--db", help="Ruta a la memoria (por omisión, la del proyecto actual)")
    p.add_argument("--tz", default=os.environ.get("FIN_TZ") or fin.local_offset(), help="Desfase, p. ej. --tz=-06:00")
    p.add_argument("--today", help="Fecha de hoy (YYYY-MM-DD), para pruebas")
    sub = p.add_subparsers(dest="command", required=True)

    def cmd(name: str, by: bool = True) -> argparse.ArgumentParser:
        s = sub.add_parser(name)
        if by:
            s.add_argument("--by", required=True)
            s.add_argument("--source", help="Palabras literales de la persona")
        return s

    cmd("activate")
    s = cmd("credit")
    s.add_argument("--key")
    s.add_argument("--name")
    s.add_argument("--update", action="store_true", help="Cambia datos de un crédito existente (--key)")
    s.add_argument("--kind", choices=["mortgage", "auto", "personal", "other"])
    s.add_argument("--lender")
    s.add_argument("--rate", help="Tasa anual en porcentaje, p. ej. 12 o 10.5")
    s.add_argument("--payment", help="Pago mensual exigible en pesos (incluye seguros y comisiones)")
    s.add_argument("--charges", help="Seguros y comisiones incluidos en el pago, en pesos")
    s.add_argument("--day", type=int, help="Día de pago del mes")
    s.add_argument("--remaining", type=int, help="Pagos que faltan (necesario si no hay tasa)")
    s.add_argument("--balance", help="Saldo real en pesos")
    s.add_argument("--balance-date", help="Fecha del saldo (YYYY-MM-DD)")
    s.add_argument("--paid-with", help="Cuenta con la que se paga (account:…)")
    s.add_argument("--prepayment", choices=["yes", "no"], help="Acepta abonos a capital sin penalización")
    s.add_argument("--since", help="Desde qué fecha se llevan sus pagos (por omisión, el día 1 de este mes)")
    s = cmd("balance")
    s.add_argument("--credit", required=True)
    s.add_argument("--amount", required=True)
    s.add_argument("--date")
    s = cmd("link")
    s.add_argument("--classifier", required=True, help="merchant:/counterparty:/kind: cuyos cargos son pagos")
    s.add_argument("--credit", required=True)
    s = cmd("pay")
    s.add_argument("--credit", required=True)
    s.add_argument("--amount", required=True)
    s.add_argument("--date")
    s.add_argument("--nonce")
    cmd("sync")
    s = cmd("income")
    s.add_argument("--key")
    s.add_argument("--name", required=True)
    s.add_argument("--amount", help="Monto por periodo en su moneda")
    s.add_argument("--currency", default="MXN")
    s.add_argument("--frequency", choices=sorted(FREQUENCY), default="monthly")
    s.add_argument("--mode", choices=["expected", "average"], default="expected")
    s.add_argument("--months", type=int, default=6, help="Meses del promedio (modo average)")
    s = cmd("fx")
    s.add_argument("--currency", required=True)
    s.add_argument("--rate", required=True, help="Pesos por unidad")
    s = cmd("cushion")
    s.add_argument("--target", required=True, help="Meta en pesos")
    s.add_argument("--account", action="append", help="Cuenta donde vive (repetible)")
    s = cmd("forecast")
    s.add_argument("--horizon", choices=list(HORIZONS), default="month")
    s.add_argument("--pace-days", type=int, default=90)
    s.add_argument("--fx", help="Tipo de cambio hipotético, p. ej. USD=17.50")
    s = cmd("plan")
    s.add_argument("--strategy", choices=["avalanche", "snowball"])
    s.add_argument("--extra", help="Abono extra al mes en pesos")
    s.add_argument("--save", action="store_true")
    s = cmd("review")
    s.add_argument("--month", required=True, help="YYYY-MM")
    cmd("cascades")
    args = p.parse_args()
    commands = {"activate": cmd_activate, "credit": cmd_credit, "balance": cmd_balance, "link": cmd_link,
                "pay": cmd_pay, "sync": cmd_sync, "income": cmd_income, "fx": cmd_fx, "cushion": cmd_cushion,
                "forecast": cmd_forecast, "plan": cmd_plan, "review": cmd_review, "cascades": cmd_cascades}
    try:
        mem = Mem(fin.find_helper(args.mem), args.db)
        mem.check_version()
        result = commands[args.command](mem, args)
        code = OK
    except FinError as exc:
        result, code = {"ok": False, "error": {"code": exc.code, "message": str(exc)}}, exc.code
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    sys.exit(code)


if __name__ == "__main__":
    main()
