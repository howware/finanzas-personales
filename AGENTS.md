# AGENTS.md

Instrucciones para agentes de IA (y personas) que **desarrollan** este repositorio. Para **usar** la
herramienta, el protocolo está en [skill/finanzas-personales/SKILL.md](skill/finanzas-personales/SKILL.md).

## Regla de oro: los datos reales nunca entran al repositorio ni al contexto

- **No abras ni extraigas texto de un estado de cuenta en PDF**, ni con herramientas de lectura ni con
  scripts propios. Solo `mxbank extract`.
- Los datos reales (PDFs, JSON de mxbank, `.memory/`, reportes) viven en la carpeta de finanzas del usuario,
  fuera de este repositorio. Nunca los copies aquí, ni siquiera temporalmente.
- Las pruebas usan los JSON de [tests/fixtures/](tests/fixtures/), generados por mxbank a partir de sus PDFs
  **sintéticos**. Para un caso nuevo, genera un PDF sintético en mxbank (`tests/synthetic/`) y extráelo con
  una llave de prueba; no edites a mano montos que deban conciliar.
- Si un valor ficticio (tarjeta, CLABE) hace falta en una prueba, constrúyelo en código como
  [tests/test_check_private_data.py](tests/test_check_private_data.py); la guardia rechaza cualquier valor
  válido escrito en un archivo.

## Dónde va cada cambio

| Cambio | Repositorio |
|---|---|
| Leer un banco nuevo, anonimizar, conciliar, ids | [mxbank](https://github.com/proteo5/mx-bank-statement-reader) |
| Almacenar, consultar, vigencia, rutas, recetas | [Long-Term Memory for AI](https://github.com/proteo5/long-term-memory-for-AI) (genérico: nada de finanzas ahí) |
| Categorías, importación, reportes, protocolo del agente | este repositorio |

Si algo de finanzas necesita rodear un límite de la memoria o de mxbank, documenta la limitación en
[docs/02-diseno.md §5](docs/02-diseno.md) y propón el cambio genérico en el repositorio correspondiente.

## Convenciones

- `fin.py` usa **solo la biblioteca estándar** y habla con la memoria a través de `memory.py`, nunca con SQL.
- Montos en la memoria: **enteros en centavos** (`MXN_cent`). Nunca `real` para dinero.
- Fechas de movimientos y periodos a **mediodía** en la zona local (una fecha a las 00:00 cambia de día al
  mostrarse en otra zona).
- Todo lo interno (claves, predicados, valores) en inglés; textos para el usuario y documentación en español.
- Predicados de enlace con `cardinality: one` cuando aplica: `first()` lo necesita en condiciones.
- Cambiar `seed.json` sube `seed_version`; cambiar el comportamiento sube la versión en `fin.py`
  (`__version__`) y se anota en [CHANGELOG.md](CHANGELOG.md).

## Comandos

```bash
git clone https://github.com/proteo5/long-term-memory-for-AI ../long-term-memory-for-AI
python -m unittest discover -s tests -v                    # pruebas (memoria real, fixtures sintéticos)
git ls-files -z | xargs -0 python tools/check_private_data.py   # guardia de datos privados
python tools/install_skill.py                              # instala el skill en ~/.claude/skills
```
