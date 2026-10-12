"""Finanzas personales sobre la memoria persistente (project-memory) y mxbank.

Comandos (salida JSON en stdout):
  setup        carga la semilla: predicados, categorías, reglas por tipo, recetas
  import       importa uno o más JSON/NDJSON de mxbank (sin duplicar)
  categorize   guarda reglas comercio/contraparte/tipo → subcategoría
  add-category crea una subcategoría
  recategorize cambia la categoría de un solo movimiento
  expense      registra un gasto o ingreso manual (efectivo)
  budget       fija el presupuesto mensual de una categoría
  report       gasto por categoría de un mes, con excepciones y presupuesto

Solo biblioteca estándar. Montos: enteros en centavos (MXN_cent).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import unicodedata
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

__version__ = "0.2.2"
HERE = Path(__file__).resolve().parent
SEED = HERE / "seed.json"
MIN_SCHEMA = (1, 1)
MIN_MEMORY = (0, 3, 0)
# categoría de un movimiento: la excepción más reciente, si hay; si no, la regla de su clasificador
CATEGORY = "first(link-in:recategorizes/link:to_category | link:classified_by/fact:categorized_as)"
# --as-of muy posterior: el último valor registrado aunque su vigencia empiece en el futuro
LATEST = "2100-01-01"
STOPWORDS = {"SUC", "SUCURSAL", "CD", "MX", "MEX", "MEXICO", "SA", "DE", "CV", "S", "A", "C", "V", "COL", "THE",
             "EL", "LA", "LOS", "Y", "EN", "WWW", "COM"}
COUNTERPARTY_KINDS = {"spei_in", "spei_out", "spei_refund", "transfer_in", "transfer_out"}


# Códigos de salida (documentados en SKILL.md)
OK, BAD_INPUT, MEMORY_ERROR = 0, 2, 3


class FinError(Exception):
    def __init__(self, message: str, code: int = BAD_INPUT):
        super().__init__(message)
        self.code = code


# -- memoria ------------------------------------------------------------------
def find_helper(explicit: str | None) -> Path:
    candidates = [explicit, os.environ.get("FIN_MEMORY_HELPER"),
                  Path.home() / ".claude/skills/project-memory/scripts/memory.py",
                  Path.home() / ".codex/skills/project-memory/scripts/memory.py"]
    for c in candidates:
        if c and Path(c).is_file():
            return Path(c)
    raise FinError("No encontré memory.py del skill project-memory. Instálalo o usa --mem / FIN_MEMORY_HELPER.",
                   MEMORY_ERROR)


class Mem:
    def __init__(self, helper: Path, db: str | None):
        self.helper, self.db = helper, db

    def check_version(self) -> None:
        cmd = [sys.executable, str(self.helper), "--version"]
        out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8").stdout
        found = re.search(r"(\d+)\.(\d+)\.(\d+)", out or "")
        if not found or tuple(int(x) for x in found.groups()) < MIN_MEMORY:
            raise FinError(f"Se necesita project-memory {'.'.join(map(str, MIN_MEMORY))} o más reciente "
                           f"(encontré: {(out or '').strip() or 'desconocida'}). Reinstala el skill.", MEMORY_ERROR)

    def run(self, *args: str, stdin: dict | None = None) -> Any:
        cmd = [sys.executable, str(self.helper)] + (["--db", self.db] if self.db else []) + list(args)
        proc = subprocess.run(cmd, input=json.dumps(stdin, ensure_ascii=False) if stdin is not None else None,
                              capture_output=True, text=True, encoding="utf-8")
        out = proc.stdout.strip()
        if proc.returncode != 0:
            raise FinError(f"memory.py {args[0]} falló: {(proc.stderr or out).strip()[-800:]}", MEMORY_ERROR)
        return json.loads(out) if out else None

    def write(self, doc: dict) -> dict:
        return self.run("write", stdin=doc)

    def rows(self, *args: str) -> list[dict]:
        return self.run("list", *args, "--limit", "1000")["rows"]


# -- utilidades -----------------------------------------------------------------
def cents(value: Any) -> int | None:
    if value is None:
        return None
    return int((Decimal(str(value)) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def money(c: int | None) -> str | None:
    if c is None:
        return None
    sign = "-" if c < 0 else ""
    return f"{sign}${abs(c) // 100:,}.{abs(c) % 100:02d}"


def at(day: str | None, tz: str, clock: str = "12:00:00") -> str | None:
    return f"{day}T{clock}{tz}" if day else None


def local_offset() -> str:
    z = datetime.now().astimezone().strftime("%z")
    return f"{z[:3]}:{z[3:]}"


def slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def merchant_name(merchant: str | None, description: str) -> str | None:
    """Nombre estable del comercio: el canónico de mxbank o las dos primeras palabras útiles."""
    if merchant:
        return merchant.strip().upper()
    text = unicodedata.normalize("NFKD", description).encode("ascii", "ignore").decode().upper()
    text = re.sub(r"\[[^\]]*\]", " ", text)
    words = [w for w in re.split(r"[^A-Z0-9&]+", text) if w and not re.search(r"\d", w) and w not in STOPWORDS]
    return " ".join(words[:2]) or None


def source(by: str, content: str, kind: str = "import") -> dict:
    return {"type": kind, "content": content, "provided_by": by, "captured_at": "now"}


def load_seed() -> dict:
    return json.loads(SEED.read_text(encoding="utf-8"))


# -- setup ------------------------------------------------------------------------
def cmd_setup(mem: Mem, args) -> dict:
    seed = load_seed()
    entities, facts = [], []
    for c in seed["categories"]:
        entities.append({"key": c["key"], "type": "category", "name": c["name"], "aliases": c.get("aliases", [])})
        general = f"{c['key']}/general"
        entities.append({"key": general, "type": "category", "name": f"{c['name']} (general)",
                         "aliases": [f"{a} (general)" for a in c.get("aliases", [])]})
        facts.append({"subject": general, "predicate": "part_of", "value": c["key"]})
    for c in seed["subcategories"]:
        entities.append({"key": c["key"], "type": "category", "name": c["name"], "aliases": c.get("aliases", [])})
        facts.append({"subject": c["key"], "predicate": "part_of", "value": c["key"].split("/")[0]})
    for kind, category in seed["kind_rules"].items():
        entities.append({"key": f"kind:{kind}", "type": "tx_kind", "name": f"Kind {kind}"})
        facts.append({"subject": f"kind:{kind}", "predicate": "categorized_as", "value": category,
                      "valid_from": "now"})
    for kind in seed["ask_kinds"]:
        entities.append({"key": f"kind:{kind}", "type": "tx_kind", "name": f"Kind {kind}"})
    entities.append({"key": "account:cash", "type": "account", "name": "Cash", "aliases": ["Efectivo"]})
    facts.append({"subject": "account:cash", "predicate": "account_product", "value": "cash"})
    result = mem.write({"source": source(args.by, f"finanzas-personales seed v{seed['seed_version']}", "helper_command"),
                        "performed_by": args.by, "predicates": [{**p, "distinct_from_similar": True} for p in seed["predicates"]],
                        "entities": entities, "facts": facts})
    mem.run("define-event-type", "--type", "transaction", "--high-volume", "--by", args.by,
            "--reason", "Imported bank transactions: hundreds per month")
    tmp = Path(os.environ.get("TEMP", "/tmp")) / f"fin-recipe-{os.getpid()}.json"
    try:
        for r in seed["recipes"]:
            tmp.write_text(json.dumps(r["definition"]), encoding="utf-8")
            mem.run("define-recipe", "--key", r["key"], "--name", r["name"], "--file", str(tmp))
    finally:
        tmp.unlink(missing_ok=True)
    return {"ok": True, "seed_version": seed["seed_version"], "warnings": result.get("warnings", []),
            "categories": len(seed["categories"]), "recipes": [r["key"] for r in seed["recipes"]]}


# -- import -----------------------------------------------------------------------
def read_statements(paths: list[str]) -> list[dict]:
    out = []
    for p in paths:
        try:
            text = sys.stdin.read() if p == "-" else Path(p).read_text(encoding="utf-8")
        except OSError as error:
            raise FinError(f"No pude leer {p}: {error.strerror or error}") from error
        text = text.strip()
        try:
            docs = [json.loads(text)] if text.startswith("{") and "\n{" not in text else \
                [json.loads(line) for line in text.splitlines() if line.strip()]
        except json.JSONDecodeError as error:
            raise FinError(f"{p} no es JSON ni NDJSON de mxbank válido (línea {error.lineno}).") from error
        out += docs
    return out


def check_statement(st: dict) -> None:
    if not st.get("ok"):
        raise FinError(f"mxbank reportó un error: {st.get('error')}")
    version = tuple(int(x) for x in str(st.get("schema_version", "0.0")).split(".")[:2])
    if version < MIN_SCHEMA or not st.get("statement_id"):
        raise FinError("Se necesita mxbank con schema 1.1 o más reciente (ids estables). Actualiza mxbank.")
    if st["privacy"].get("pseudonym_scope") != "key":
        raise FinError("El JSON se generó sin --pseudonym-key-env: sus ids cambian en cada ejecución y "
                       "duplicarían movimientos. Vuelve a extraer con la misma llave de siempre.")
    if not st["account"].get("account_ref"):
        raise FinError("El estado no trae account_ref: no se puede saber a qué cuenta pertenece.")


def classifier(tx: dict, seed: dict) -> tuple[str, dict | None]:
    """Entidad cuya regla de categoría aplica al movimiento: tipo, contraparte o comercio."""
    kind = tx["type"]
    if kind in seed["kind_rules"]:
        return f"kind:{kind}", None
    ref = tx.get("counterparty_ref") or tx.get("counterparty_account_ref")
    if ref:
        return f"counterparty:{ref}", {"key": f"counterparty:{ref}", "type": "counterparty", "name": ref}
    if kind in COUNTERPARTY_KINDS or kind == "cash_deposit":
        return f"kind:{kind}", {"key": f"kind:{kind}", "type": "tx_kind", "name": f"Kind {kind}"}
    name = merchant_name(tx.get("merchant"), tx.get("description") or "")
    if not name:
        return f"kind:{kind}", {"key": f"kind:{kind}", "type": "tx_kind", "name": f"Kind {kind}"}
    key = f"merchant:{slug(name)}"
    return key, {"key": key, "type": "merchant", "name": name}


def statement_document(st: dict, by: str, tz: str, seed: dict) -> tuple[dict, dict]:
    doc_, acct, period = st["document"], st["account"], st["period"]
    credit = st.get("credit") or {}
    account_key = f"account:{acct['account_ref']}"
    product = doc_["product"]
    label = doc_.get("product_name") or f"{doc_['bank_name']} {product}"
    name = f"{label} ({acct['account_last4']})" if acct.get("account_last4") else label
    end_instant = at(period.get("end"), tz)
    entities = {account_key: {"key": account_key, "type": "account", "name": name}}
    facts = [{"subject": account_key, "predicate": "account_product", "value": product},
             {"subject": account_key, "predicate": "bank_code", "value": doc_["bank"]}]
    if product == "credit":
        if credit.get("total_balance") is not None and end_instant:
            facts.append({"subject": account_key, "predicate": "balance", "value": -cents(credit["total_balance"]),
                          "valid_from": end_instant})
        if credit.get("credit_limit") is not None and end_instant:
            facts.append({"subject": account_key, "predicate": "credit_limit", "value": cents(credit["credit_limit"]),
                          "valid_from": end_instant})
    elif (st.get("summary") or {}).get("closing_balance") is not None and end_instant:
        facts.append({"subject": account_key, "predicate": "balance", "value": cents(st["summary"]["closing_balance"]),
                      "valid_from": end_instant})

    attrs: dict[str, Any] = {"period_start": at(period.get("start"), tz), "period_end": end_instant,
                             "reconciled": st["validation"].get("reconciled")}
    summary = st.get("summary") or {}
    for k in ("opening_balance", "closing_balance"):
        attrs[k] = cents(summary.get(k))
    for k in ("no_interest_payment", "minimum_payment", "interest_charged", "fees_charged",
              "vat_on_interest_and_fees", "total_balance"):
        attrs[k] = cents(credit.get(k))
    attrs["payment_due_date"] = at(credit.get("payment_due_date"), tz)
    attrs = {k: v for k, v in attrs.items() if v is not None}
    sid = st["statement_id"]
    events = [{"key": sid, "type": "statement_imported", "occurred_at": end_instant or "now",
               "summary": f"{name} statement {period.get('start')}..{period.get('end')}",
               "attributes": attrs, "links": [{"predicate": "on_account", "entity": account_key}]}]

    no_interest = cents(credit.get("no_interest_payment"))
    due = None
    if product == "credit" and no_interest and no_interest > 0 and credit.get("payment_due_date"):
        due = {"key": f"DUE_{sid}", "due_date": credit["payment_due_date"], "no_interest": no_interest}
        events.append({"key": due["key"], "type": "payment_due", "occurred_at": end_instant,
                       "summary": f"Pay {money(no_interest)} on {name} by {credit['payment_due_date']}",
                       "attributes": {"payment_due_date": attrs["payment_due_date"], "no_interest_payment": no_interest,
                                      **({"minimum_payment": attrs["minimum_payment"]} if "minimum_payment" in attrs else {}),
                                      "requested_action": f"Pay {money(no_interest)} (no-interest payment) on {name} "
                                                          f"by {credit['payment_due_date']}"},
                       "pending_for": by,
                       "links": [{"predicate": "on_account", "entity": account_key},
                                 {"predicate": "for_statement", "event": sid}]})

    touched: dict[str, dict] = {}
    for tx in st["transactions"]:
        ckey, cent = classifier(tx, seed)
        if cent:
            entities.setdefault(ckey, cent)
        amount = cents(tx["amount"])
        t = touched.setdefault(ckey, {"classifier": ckey, "name": (cent or {}).get("name", ckey),
                                      "transactions": 0, "amount_cents": 0})
        t["transactions"] += 1
        t["amount_cents"] += amount
        tattrs = {"amount": amount, "tx_type": tx["type"], "bank_description": tx.get("description"),
                  "entry_source": "statement", "original_currency": tx.get("original_currency"),
                  "original_amount_text": tx.get("original_amount"), "exchange_rate_text": tx.get("exchange_rate"),
                  "installment_number": tx.get("installment_number"), "installments_total": tx.get("installments_total")}
        events.append({"key": tx["id"], "type": "transaction", "occurred_at": at(tx["date"], tz),
                       "summary": (tx.get("description") or tx["type"])[:160],
                       "attributes": {k: v for k, v in tattrs.items() if v is not None},
                       "links": [{"predicate": "on_account", "entity": account_key},
                                 {"predicate": "classified_by", "entity": ckey},
                                 {"predicate": "imported_from", "event": sid}]})

    for plan in st.get("installment_plans") or []:
        pkey = f"plan:{plan['id']}"
        entities[pkey] = {"key": pkey, "type": "installment_plan", "name": plan["description"]}
        facts.append({"subject": pkey, "predicate": "on_account", "value": account_key})
        for pred, value in (("plan_original_amount", cents(plan.get("original_amount"))),
                            ("installments_total", plan.get("installments_total"))):
            if value is not None:
                facts.append({"subject": pkey, "predicate": pred, "value": value})
        for pred, value in (("pending_balance", cents(plan.get("pending_balance"))),
                            ("installments_paid", plan.get("installment_number"))):
            if value is not None and end_instant:
                facts.append({"subject": pkey, "predicate": pred, "value": value, "valid_from": end_instant})

    write = {"source": source(by, f"mxbank statement {sid} ({doc_['bank']} {product} {period.get('start')}..{period.get('end')})"),
             "performed_by": by, "entities": list(entities.values()), "facts": facts, "events": events}
    info = {"statement_id": sid, "account": account_key, "account_name": name, "product": product,
            "period": [period.get("start"), period.get("end")], "reconciled": st["validation"].get("reconciled"),
            "warnings": st["validation"].get("warnings", []), "due": due, "touched": touched,
            "payments": [(tx["date"], cents(tx["amount"])) for tx in st["transactions"] if tx["type"] == "card_payment"]}
    return write, info


def settle(mem: Mem, by: str, tz: str, account: str, prev_sid: str, next_payments: list[tuple[str, int]]) -> dict | None:
    """Cierra el pago pendiente de prev_sid con los pagos del estado siguiente hechos a tiempo."""
    dues = mem.rows("--event-type", "payment_due", "--where", f"link:for_statement/key = {prev_sid}",
                    "--column", "key", "--column", "attr:payment_due_date", "--column", "attr:no_interest_payment")
    if not dues:
        return None
    due = dues[0]
    due_day = str(due["attr:payment_due_date"])[:10]
    paid = sum(a for d, a in next_payments if d <= due_day and a > 0)
    shortfall = max(0, due["attr:no_interest_payment"] - paid)
    mem.write({"source": source(by, f"payments found for {due['key']}"), "performed_by": by,
               "events": [{"key": f"PAID_{prev_sid}", "type": "payment_due_settled", "occurred_at": at(due_day, tz),
                           "summary": f"Paid {money(paid)} of {money(due['attr:no_interest_payment'])} by {due_day}",
                           "attributes": {"paid_amount": paid, "shortfall": shortfall, "covered": shortfall == 0},
                           "links": [{"predicate": "resolves", "event": due["key"]},
                                     {"predicate": "on_account", "entity": account}]}]})
    return {"due": due["key"], "paid": money(paid), "shortfall": money(shortfall), "covered": shortfall == 0}


def neighbours(mem: Mem, account: str, start: str, end: str) -> tuple[dict | None, dict | None]:
    rows = mem.rows("--event-type", "statement_imported", "--where", f"link:on_account = {account}",
                    "--column", "key", "--column", "attr:period_start", "--column", "attr:period_end")
    prev = [r for r in rows if r["attr:period_end"] and str(r["attr:period_end"])[:10] < start]
    nxt = [r for r in rows if r["attr:period_start"] and str(r["attr:period_start"])[:10] > end]
    return (max(prev, key=lambda r: str(r["attr:period_end"])) if prev else None,
            min(nxt, key=lambda r: str(r["attr:period_start"])) if nxt else None)


def payments_of(mem: Mem, sid: str) -> list[tuple[str, int]]:
    rows = mem.rows("--event-type", "transaction", "--where", f"link:imported_from/key = {sid}",
                    "--where", "attr:tx_type = card_payment", "--column", "occurred_at", "--column", "attr:amount")
    return [(str(r["occurred_at"])[:10], r["attr:amount"]) for r in rows]


TEMPORAL = {"balance", "credit_limit", "pending_balance", "installments_paid"}


def drop_older_facts(mem: Mem, facts: list[dict]) -> tuple[list[dict], int]:
    """Un estado viejo importado después de uno nuevo no reemplaza saldos vigentes (ya quedan en el evento)."""
    keep, skipped, current = [], 0, {}
    for subject in {f["subject"] for f in facts if f["predicate"] in TEMPORAL}:
        etype = "account" if subject.startswith("account:") else "installment_plan"
        cols = [x for pred in sorted(TEMPORAL) for x in ("--column", f"fact:{pred}/since")]
        rows = mem.rows("--entity-type", etype, "--where", f"key = {subject}", "--as-of", LATEST, *cols)
        if rows:
            current[subject] = rows[0]
    for f in facts:
        since = current.get(f["subject"], {}).get(f"fact:{f['predicate']}/since") if f["predicate"] in TEMPORAL else None
        if since and f.get("valid_from") and parse_instant(f["valid_from"]) <= parse_instant(str(since)):
            skipped += 1
            continue
        keep.append(f)
    return keep, skipped


def parse_instant(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def quiet(warnings: list[str]) -> list[str]:
    # los movimientos de débito y crédito traen atributos distintos a propósito
    return [w for w in warnings if "attributes differ from earlier events" not in w]


def event_key(item: Any) -> str:
    return str(item.get("key") or item.get("external_key") or "") if isinstance(item, dict) else str(item)


def cmd_import(mem: Mem, args) -> dict:
    seed = load_seed()
    statements = read_statements(args.files)
    for st in statements:
        check_statement(st)
    statements.sort(key=lambda s: (s["period"].get("start") or ""))
    report, all_touched = [], {}
    for st in statements:
        doc, info = statement_document(st, args.by, args.tz, seed)
        if args.dry_run:
            report.append({"statement_id": info["statement_id"], "events": len(doc["events"]), "dry_run": True})
            continue
        doc["facts"], skipped = drop_older_facts(mem, doc["facts"])
        result = mem.write(doc)
        ev = result.get("events", {})
        entry = {"statement_id": info["statement_id"], "account": info["account_name"],
                 "period": info["period"], "reconciled": info["reconciled"],
                 "transactions_new": sum(1 for e in ev.get("created", []) if event_key(e).startswith("TX_")),
                 "transactions_existing": sum(1 for e in ev.get("existing", []) if event_key(e).startswith("TX_")),
                 "warnings": info["warnings"] + quiet(result.get("warnings", []))}
        if skipped:
            entry["older_than_current"] = skipped
        if info["product"] == "credit":
            prev, nxt = neighbours(mem, info["account"], *info["period"])
            settled = []
            if prev:
                s = settle(mem, args.by, args.tz, info["account"], prev["key"], info["payments"])
                if s:
                    settled.append(s)
            if nxt and info["due"]:
                s = settle(mem, args.by, args.tz, info["account"], info["statement_id"], payments_of(mem, nxt["key"]))
                if s:
                    settled.append(s)
            if settled:
                entry["payments_settled"] = settled
        report.append(entry)
        for k, t in info["touched"].items():
            agg = all_touched.setdefault(k, {**t, "transactions": 0, "amount_cents": 0})
            agg["transactions"] += t["transactions"]
            agg["amount_cents"] += t["amount_cents"]
    out: dict[str, Any] = {"ok": True, "statements": report}
    if not args.dry_run:
        unruled = set()
        for etype in ("merchant", "counterparty", "tx_kind"):
            unruled |= {r["key"] for r in mem.rows("--entity-type", etype, "--where", "no:fact:categorized_as",
                                                   "--column", "key")}
        to_classify = sorted((t for k, t in all_touched.items() if k in unruled), key=lambda t: t["amount_cents"])
        out["to_classify"] = [{"classifier": t["classifier"], "name": t["name"], "transactions": t["transactions"],
                               "amount": money(t["amount_cents"])} for t in to_classify]
        out["pending"] = mem.run("pending")
    return out


# -- categorías y capturas ----------------------------------------------------------------
def cmd_categorize(mem: Mem, args) -> dict:
    facts, rules = [], []
    for rule in args.rule:
        who, _, category = rule.partition("=")
        if not category.startswith("category:") or "/" not in category:
            raise FinError(f"La regla {rule!r} debe apuntar a una subcategoría (category:<grupo>/<sub>).")
        facts.append({"subject": who.strip(), "predicate": "categorized_as", "value": category.strip(), "valid_from": "now"})
        rules.append({"classifier": who.strip(), "category": category.strip()})
    result = mem.write({"source": source(args.by, args.source or "category rules", "user_statement"),
                        "performed_by": args.by, "facts": facts})
    return {"ok": True, "rules": rules, "warnings": quiet(result.get("warnings", []))}


def cmd_add_category(mem: Mem, args) -> dict:
    key = args.key
    if not re.fullmatch(r"category:[a-z0-9-]+/[a-z0-9-]+", key):
        raise FinError("Solo se crean subcategorías: category:<grupo>/<sub> en minúsculas con guiones.")
    parent = key.split("/")[0]
    result = mem.write({"source": source(args.by, args.source or f"new category {key}", "user_statement"),
                        "performed_by": args.by,
                        "entities": [{"key": key, "type": "category", "name": args.name, "aliases": args.alias or []}],
                        "facts": [{"subject": key, "predicate": "part_of", "value": parent}]})
    return {"ok": True, "category": key, "parent": parent, "warnings": quiet(result.get("warnings", []))}


def cmd_recategorize(mem: Mem, args) -> dict:
    previous = mem.rows("--event-type", "transaction_recategorized", "--where", f"link:recategorizes/key = {args.tx}",
                        "--column", "key")
    doc: dict[str, Any] = {"source": source(args.by, args.source or f"recategorize {args.tx}", "user_statement"),
                           "performed_by": args.by}
    if previous:
        doc["void"] = [{"event": p["key"], "reason": "Replaced by a newer category choice"} for p in previous]
    n = len(previous) + 1
    doc["events"] = [{"key": f"RECAT_{args.tx}_{n}", "type": "transaction_recategorized", "occurred_at": "now",
                      "summary": f"{args.tx} → {args.to}" + (f": {args.reason}" if args.reason else ""),
                      **({"attributes": {"rationale": args.reason}} if args.reason else {}),
                      "links": [{"predicate": "recategorizes", "event": args.tx},
                                {"predicate": "to_category", "entity": args.to}]}]
    result = mem.write(doc)
    return {"ok": True, "transaction": args.tx, "category": args.to, "replaced": [p["key"] for p in previous],
            "warnings": quiet(result.get("warnings", []))}


def cmd_expense(mem: Mem, args) -> dict:
    amount = cents(args.amount)
    amount = amount if args.income else -abs(amount)
    day = args.date or date.today().isoformat()
    account = args.account or "account:cash"
    key = "MAN_" + hashlib.sha256(f"{account}|{day}|{amount}|{args.description}|{args.nonce or ''}".encode()).hexdigest()[:16]
    ckey = args.classifier
    entities = []
    if not ckey:
        name = merchant_name(None, args.description) or "MANUAL"
        ckey = f"merchant:{slug(name)}"
        entities.append({"key": ckey, "type": "merchant", "name": name})
    event = {"key": key, "type": "transaction", "occurred_at": at(day, args.tz), "summary": args.description[:160],
             "attributes": {"amount": amount, "tx_type": "manual", "entry_source": "manual",
                            "bank_description": args.description},
             "links": [{"predicate": "on_account", "entity": account}, {"predicate": "classified_by", "entity": ckey}]}
    result = mem.write({"source": source(args.by, args.source or args.description, "user_statement"),
                        "performed_by": args.by, "entities": entities, "events": [event]})
    created = bool(result.get("events", {}).get("created"))
    return {"ok": True, "key": key, "amount": money(amount), "classifier": ckey, "created": created,
            "warnings": quiet(result.get("warnings", []))}


def cmd_budget(mem: Mem, args) -> dict:
    month = datetime.strptime(args.month, "%Y-%m")
    result = mem.write({"source": source(args.by, args.source or f"budget {args.category} {args.amount}", "user_statement"),
                        "performed_by": args.by,
                        "facts": [{"subject": args.category, "predicate": "monthly_budget", "value": cents(args.amount),
                                   "valid_from": at(f"{month:%Y-%m}-01", args.tz)}]})
    return {"ok": True, "category": args.category, "monthly_budget": money(cents(args.amount)), "from": args.month,
            "warnings": quiet(result.get("warnings", []))}


# -- reportes --------------------------------------------------------------------------
def month_bounds(month: str) -> tuple[str, str]:
    start = datetime.strptime(month, "%Y-%m").date()
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return start.isoformat(), end.isoformat()


def cmd_report(mem: Mem, args) -> dict:
    """Gasto neto del mes por categoría (excepciones primero, luego reglas) y presupuesto en vigor."""
    start, end = month_bounds(args.month)
    top_path = f"{CATEGORY}/fact:part_of/key"
    by = ["--by", top_path] + (["--by", f"{CATEGORY}/key"] if args.level == "sub" else [])
    groups = mem.run("aggregate", "--event-type", "transaction", "--measure", "sum:amount", "--since", start,
                     "--until", end, "--where", f"{CATEGORY}/fact:part_of != category:internal", *by)["groups"]
    totals: dict[str, int] = {}
    counts: dict[str, int] = {}
    income = spending = uncategorized = 0
    for g in groups:
        top = g[top_path]
        cat = (g[f"{CATEGORY}/key"] if args.level == "sub" else top) or "uncategorized"
        amount = g["value"] or 0
        totals[cat] = totals.get(cat, 0) + amount
        counts[cat] = counts.get(cat, 0) + g["rows"]
        if cat == "uncategorized":
            uncategorized += amount
        elif top == "category:income":
            income += amount
        else:
            spending += amount
    # presupuesto en vigor durante el mes (vale desde el día 1); en nivel "top" se suman sus subcategorías
    budgets: dict[str, int] = {}
    for r in mem.rows("--entity-type", "category", "--where", "has:fact:monthly_budget", "--as-of", end,
                      "--column", "key", "--column", "fact:monthly_budget"):
        target = r["key"] if args.level == "sub" else r["key"].split("/")[0]
        budgets[target] = budgets.get(target, 0) + r["fact:monthly_budget"]
    lines = []
    for cat, total in sorted(totals.items(), key=lambda kv: kv[1]):
        line = {"category": cat, "net": money(total), "net_cents": total, "transactions": counts[cat]}
        if cat in budgets:
            line["budget"] = money(budgets[cat])
            line["budget_left"] = money(budgets[cat] + total)
        lines.append(line)
    return {"ok": True, "month": args.month, "level": args.level, "income": money(income), "spending": money(spending),
            "uncategorized": money(uncategorized), "net": money(income + spending + uncategorized),
            "categories": lines, "budgets_without_spending": [
                {"category": k, "budget": money(v)} for k, v in budgets.items() if k not in totals],
            "note": "Excluye movimientos internos (pagos a tarjeta, traspasos propios, retiros, traslados a meses)."}


# -- CLI --------------------------------------------------------------------------------
def main() -> None:
    p = argparse.ArgumentParser(prog="fin.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"fin.py {__version__}")
    p.add_argument("--mem", help="Ruta a memory.py (por omisión, el skill project-memory instalado)")
    p.add_argument("--db", help="Ruta a la memoria (por omisión, la del proyecto actual)")
    p.add_argument("--tz", default=os.environ.get("FIN_TZ") or local_offset(), help="Desfase de la zona horaria, p. ej. --tz=-06:00 (por omisión, la del sistema)")
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("setup")
    s.add_argument("--by", required=True)
    s = sub.add_parser("import")
    s.add_argument("files", nargs="+", help="JSON o NDJSON de mxbank; '-' para stdin")
    s.add_argument("--by", required=True)
    s.add_argument("--dry-run", action="store_true")
    s = sub.add_parser("categorize")
    s.add_argument("--rule", action="append", required=True, help="merchant:x=category:grupo/sub (repetible)")
    s.add_argument("--by", required=True)
    s.add_argument("--source", help="Palabras literales de la persona")
    s = sub.add_parser("add-category")
    s.add_argument("--key", required=True)
    s.add_argument("--name", required=True)
    s.add_argument("--alias", action="append")
    s.add_argument("--by", required=True)
    s.add_argument("--source")
    s = sub.add_parser("recategorize")
    s.add_argument("tx")
    s.add_argument("--to", required=True)
    s.add_argument("--reason")
    s.add_argument("--by", required=True)
    s.add_argument("--source")
    s = sub.add_parser("expense")
    s.add_argument("--amount", required=True, help="Monto en pesos, positivo")
    s.add_argument("--description", required=True)
    s.add_argument("--date", help="YYYY-MM-DD (hoy por omisión)")
    s.add_argument("--account", help="Cuenta (account:cash por omisión)")
    s.add_argument("--classifier", help="merchant:/counterparty:/kind: existente")
    s.add_argument("--income", action="store_true", help="Es una entrada de dinero")
    s.add_argument("--nonce", help="Distingue dos capturas idénticas el mismo día")
    s.add_argument("--by", required=True)
    s.add_argument("--source")
    s = sub.add_parser("budget")
    s.add_argument("--category", required=True)
    s.add_argument("--amount", required=True, help="Pesos por mes")
    s.add_argument("--month", default=date.today().strftime("%Y-%m"), help="Desde qué mes (YYYY-MM)")
    s.add_argument("--by", required=True)
    s.add_argument("--source")
    s = sub.add_parser("report")
    s.add_argument("--month", required=True, help="YYYY-MM")
    s.add_argument("--level", choices=["top", "sub"], default="top")
    args = p.parse_args()
    commands = {"setup": cmd_setup, "import": cmd_import, "categorize": cmd_categorize, "add-category": cmd_add_category,
                "recategorize": cmd_recategorize, "expense": cmd_expense, "budget": cmd_budget, "report": cmd_report}
    try:
        mem = Mem(find_helper(args.mem), args.db)
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
