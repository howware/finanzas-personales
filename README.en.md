<h1 align="center">finanzas-personales · Personal finance without an app, with AI</h1>

<p align="center">
  <b>Import your bank statements, categorize, budget and ask questions, all in a conversation with your AI agent.</b><br>
  Privacy by design: your personal data never reaches the AI · 100 % local · Claude Code and Codex
</p>

<p align="center">
  <a href="https://github.com/proteo5/finanzas-personales/actions/workflows/ci.yml"><img src="https://github.com/proteo5/finanzas-personales/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/version-0.1.0-blue" alt="Version 0.1.0">
  <img src="https://img.shields.io/badge/python-3.9%2B-blue" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/license-Apache%202.0-green" alt="Apache 2.0 license">
</p>

<p align="center">
  <a href="https://proteo5.github.io/finanzas-personales/">Project site</a> ·
  <a href="README.md">Español</a>
</p>

A personal finance app is four things: **capture** of transactions, a **database**, **rules** (categories,
budgets) and **screens**. With an AI agent the screen is the conversation, and three local, open tools do the
rest:

| App piece | Here |
|---|---|
| Capture | [mxbank](https://github.com/proteo5/mx-bank-statement-reader): reads Mexican bank statement PDFs on your machine and outputs JSON without personal data |
| Database | [Long-Term Memory for AI](https://github.com/proteo5/long-term-memory-for-AI): a local, append-only SQLite file with history |
| Rules | **this repo**: the `finanzas-personales` skill and `fin.py` |
| Screens | the conversation with Claude Code or Codex |

The project targets Mexico: banks supported by mxbank (BBVA debit and credit, BanCoppel debit), MXN, and the
agent talks in the user's language. Full documentation is in Spanish: see [README.md](README.md).

## Privacy by design

This project started from one question: **how do you use AI with your finances without handing over your
identity?** A bank statement carries your name, address, tax id, card and account numbers, and the names and
accounts of the people you pay. Uploading it to an AI chat gives all of that to a third party.

Here **the statement never goes to the AI**. It is read on your computer, everything that identifies you is
removed right there, and the agent only works with what is left: anonymous transactions.

| 🔒 Stays on your computer, never reaches the AI | What the AI does see, so it can answer you |
|---|---|
| The statement PDF, in full | Merchant, amount and date of each transaction |
| Your name, address, RFC and CURP | Categories, budgets and totals |
| Card and account numbers, CLABE | Pseudonyms instead of accounts (`ACC_92d5`) and people (`PERSONA_7f3a`) |
| Names and accounts of the people you pay | Product name and last 4 digits of the account (can be omitted) |
| The memory file: the agent queries it and only sees the answers | What you type in the conversation |

How it is enforced: the skill forbids the agent from opening the PDF; only mxbank reads it, offline; its output
is built from a closed list of fields; a final scanner withholds the whole result if it finds anything that
looks personal; counterparties are pseudonymized with a key only you hold; mxbank, `fin.py` and the memory make
no network connections; and CI blocks real data from ever being committed.

> **To be precise:** what the agent does see (merchants, amounts, dates, pseudonyms) is sent to your AI
> provider under its terms. It does not identify you on its own, but it is still information about your
> spending habits.

## Features

- **Statement import** that never duplicates, in any order, thanks to mxbank's stable ids.
- **Categories that learn.** Fix a merchant once and its whole history is reclassified; one-off exceptions
  don't break the rule.
- **Cash in one sentence**, recorded with your own words as evidence.
- **Budgets with history**, per category and month.
- **Card payments**: every session starts with the no-interest payment and due date; it closes itself when
  the next statement shows the payment.
- **Instant reports**: spending by category, month over month, active installment plans, interest and fees.
- **Nothing is erased**: changes close or void records, with author, date and reason.

## Install

```bash
git clone https://github.com/proteo5/mx-bank-statement-reader
cd mx-bank-statement-reader && uv tool install . && cd ..
git clone https://github.com/proteo5/long-term-memory-for-AI
python long-term-memory-for-AI/tools/install_skill.py --target ~/.claude/skills/project-memory
git clone https://github.com/proteo5/finanzas-personales
python finanzas-personales/tools/install_skill.py
```

Set a long random `MXBANK_KEY` environment variable once and back it up: it keeps ids and pseudonyms stable
across months. Then create a folder for your finances, open Claude Code or Codex there and say
*"Quiero llevar mis finanzas aquí"* (or the same in English).

## License

[Apache 2.0](LICENSE), provided as is, without warranty. A personal organization tool; **not financial, tax or
legal advice**. Not affiliated with or endorsed by any bank. See the [legal notice](AVISO-LEGAL.md) (Spanish).
