# finanzas-personales

Lleva tus finanzas personales con un agente de IA (Claude Code o Codex), sin app: importas tus estados de
cuenta, categorizas, capturas el efectivo, fijas presupuestos y preguntas, todo en la conversación.

Se apoya en dos herramientas locales:

- [mxbank](https://github.com/proteo5/mx-bank-statement-reader) ≥ 0.2.0: lee estados de cuenta mexicanos en
  PDF y entrega JSON sin datos personales, con ids estables.
- [long-term-memory-for-AI](https://github.com/proteo5/long-term-memory-for-AI) ≥ 0.3.0: memoria SQLite
  local, solo de agregado, que el agente consulta y actualiza.

Este repo agrega el skill `finanzas-personales`: el protocolo para el agente y `fin.py`, que importa el JSON de
mxbank a la memoria y arma los reportes. Todo corre en tu máquina.

## Instalación

Requiere Python 3.9+ y los skills `mxbank` y `project-memory` instalados (ver sus README).

```bash
# Claude Code (macOS / Linux / Git Bash)
mkdir -p ~/.claude/skills && cp -r skill/finanzas-personales ~/.claude/skills/
```

```powershell
# Claude Code (Windows PowerShell)
Copy-Item -Recurse -Force skill\finanzas-personales "$HOME\.claude\skills\"
```

Para Codex, copia la misma carpeta a `~/.codex/skills/`.

Define una llave privada y fija para los seudónimos de mxbank, una sola vez (variable de entorno de tu usuario,
`MXBANK_KEY`). Si la cambias, los ids cambian y los movimientos se importarían de nuevo.

## Uso

Crea una carpeta para tus finanzas, abre ahí el agente y pídele, por ejemplo:

- "Quiero llevar mis finanzas aquí." → crea la memoria y carga categorías.
- "Importa los estados de `estados/2026-09/`." → mxbank + importación; te propone categorías para lo nuevo.
- "Ayer gasté 180 en efectivo en la fonda."
- "Pon 4,000 al mes para súper." · "¿Cómo voy este mes?" · "¿Qué tarjetas tengo que pagar?"
- "Hagamos el cierre de septiembre."

Agrega a `CLAUDE.md` / `AGENTS.md` de esa carpeta la instrucción de memoria persistente del README de
long-term-memory-for-AI, y a `.gitignore`: `estados/`, `reportes/`, `.memory/`.

## Documentación

| Documento | Contenido |
|---|---|
| [01 · Análisis](docs/01-analisis.md) | Qué hace una app de finanzas personales y cómo se cubre sin app |
| [02 · Diseño](docs/02-diseno.md) | Decisiones, modelo en la memoria, limitaciones conocidas |
| [SKILL.md](skill/finanzas-personales/SKILL.md) | El protocolo que sigue el agente |

## Desarrollo

```bash
python -m unittest discover -s tests -v
```

Las pruebas usan una memoria temporal y JSON generados por mxbank a partir de sus PDFs **sintéticos**. Buscan el
helper de la memoria en `FIN_MEMORY_HELPER`, en `../long-term-memory-for-AI/db/memory.py` o en el skill instalado.
Nunca agregues estados de cuenta reales ni sus JSON al repo.

## Aviso

Herramienta de organización personal, sin garantías. No es asesoría financiera, fiscal ni legal; verifica las
cifras contra tus estados de cuenta.

## Licencia

[Apache 2.0](LICENSE).
