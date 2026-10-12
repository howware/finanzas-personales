<h1 align="center">finanzas-personales · Personal finance without an app, with AI</h1>

<p align="center">
  <b>Import your bank statements, categorize, budget and ask questions, all in a conversation with your AI agent.</b><br>
  Privacy by design · read and stored on your computer · open source and auditable · Claude Code and Codex
</p>

<p align="center">
  <a href="https://github.com/howware/finanzas-personales/actions/workflows/ci.yml"><img src="https://github.com/howware/finanzas-personales/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/version-0.2.1-blue" alt="Version 0.2.1">
  <a href="https://howware.org"><img src="https://img.shields.io/badge/howware-0.1-5a45d6" alt="howware 0.1"></a>
  <img src="https://img.shields.io/badge/python-3.9%2B-blue" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/license-Apache%202.0-green" alt="Apache 2.0 license">
</p>

<p align="center">
  <a href="https://howware.org/finanzas-personales/">Project site</a> ·
  <a href="README.md">Español</a>
</p>

> **The first [howware](https://howware.org).** A howware is your know-how, put to work by AI: you state the rules
> in your own words and an agent follows them, with a few exact tools and a memory you own. No app to build, no
> one to hand it off to, no waiting. This repository conforms to the
> [howware specification 0.1](https://github.com/howware/howware/blob/main/docs/spec.md); its manifest is
> [`howware.json`](howware.json).

A personal finance app is four things: **capture** of transactions, a **database**, **rules** (categories,
budgets) and **screens**. With an AI agent the screen is the conversation, and three local, open tools do the
rest:

| App piece | Here |
|---|---|
| Capture | [mxbank](https://github.com/howware/mx-bank-statement-reader): reads Mexican bank statement PDFs on your machine and outputs anonymized JSON |
| Database | [Long-Term Memory for AI](https://github.com/howware/long-term-memory-for-AI): a local, append-only SQLite file with history |
| Rules | **this repo**: the `finanzas-personales` skill and `fin.py` |
| Screens | the conversation with Claude Code or Codex |

The project targets Mexico: banks supported by mxbank (BBVA debit and credit, BanCoppel debit), MXN, and the
agent talks in the user's language. Full documentation is in Spanish: see [README.md](README.md).

## Privacy by design

This project started from one question: **how do you use AI with your finances without handing over your
identity?** A bank statement carries your name, address, tax id, card and account numbers, and the names and
accounts of the people you pay. Uploading it to an AI chat gives all of that to a third party.

So it is built so that **the statement is not handed to the AI**: it is read on your computer, what identifies
you is removed right there, and the agent works with what is left: transactions without your name or accounts.

| 🔒 Designed to stay on your computer | What the AI does see, so it can answer you |
|---|---|
| The statement PDF | Merchant, amount and date of each transaction |
| Your name, address, RFC and CURP | Categories, budgets and totals |
| Card and account numbers, CLABE | Pseudonyms instead of accounts (`ACC_92d5`) and people (`PERSONA_7f3a`) |
| Names and accounts of the people you pay | Product name and last 4 digits of the account (can be omitted) |
| The memory file (the agent queries it and sees the answers) | What you type in the conversation |

**How it is built:** the skill forbids the agent from opening the PDF and only mxbank reads it; mxbank's output
is a closed list of fields; a final scanner withholds the whole result if anything looks personal;
counterparties are pseudonymized with a key only you hold; mxbank, `fin.py` and the memory open no network
connections; CI blocks real data from being committed. The Spanish [README](README.md#cómo-está-construido)
links each measure to the code that implements it.

**What we cannot guarantee:** automatic anonymization is not infallible; the no-PDF rule is an instruction to
the agent (in Claude Code you can back it with a `Read(**/*.pdf)` deny permission, which still is not an
absolute barrier); what the agent does see leaves your computer for your AI provider, under its terms; and the
memory file is not encrypted.

**Open source so you can check it.** We don't ask for trust, we ask you to review it. All three pieces are
Apache 2.0 and small on purpose: [finanzas-personales](https://github.com/howware/finanzas-personales),
[mxbank](https://github.com/howware/mx-bank-statement-reader),
[Long-Term Memory for AI](https://github.com/howware/long-term-memory-for-AI). Found a privacy problem? Report
it privately via [SECURITY.md](SECURITY.md).

## Features

- **Designed so your personal data does not reach the AI**, and open source so anyone can verify it.
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
git clone https://github.com/howware/mx-bank-statement-reader
cd mx-bank-statement-reader && uv tool install . && cd ..
git clone https://github.com/howware/long-term-memory-for-AI
python long-term-memory-for-AI/tools/install_skill.py --target ~/.claude/skills/project-memory
git clone https://github.com/howware/finanzas-personales
python finanzas-personales/tools/install_skill.py
```

**Tested on Claude Code.** It is written for Codex too, but has not been tested there yet.

Set a long random `MXBANK_KEY` environment variable once and back it up: it keeps ids and pseudonyms stable
across months. Then create a folder for your finances, open Claude Code or Codex there and say
*"Quiero llevar mis finanzas aquí"* (or the same in English).

## License

[Apache 2.0](LICENSE), provided as is, without warranty. A personal organization tool; **not financial, tax or
legal advice**. Not affiliated with or endorsed by any bank. See the [legal notice](AVISO-LEGAL.md) (Spanish).
