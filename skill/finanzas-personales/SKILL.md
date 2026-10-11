---
name: finanzas-personales
description: Lleva las finanzas personales del usuario sin app, sobre la memoria persistente (project-memory) y estados de cuenta leídos con mxbank. Úsalo cuando el usuario quiera importar estados de cuenta a su historial, categorizar gastos, registrar un gasto en efectivo, fijar o revisar presupuestos, saber cuánto gastó o ganó por categoría o mes, qué pagos de tarjeta tiene pendientes, o hacer el cierre de mes.
---

# Finanzas personales sin app

Tres piezas, cada una con su responsabilidad:

Requiere `project-memory` 0.3.0 o más reciente y `mxbank` 0.2.0 o más reciente; `fin.py` lo verifica.

| Pieza | Hace | Nunca |
|---|---|---|
| `mxbank` (skill `mxbank`) | Lee el PDF localmente y entrega JSON anonimizado con ids estables | — |
| `fin.py` (este skill, `scripts/fin.py`) | Importa ese JSON a la memoria, guarda reglas, captura efectivo, arma reportes | Leer PDFs |
| Memoria (skill `project-memory`) | Guarda todo, sin borrar, con historia | — |

`FIN` = `python "<carpeta de este skill>/scripts/fin.py"`; `MEM` = el helper del skill `project-memory`.
Ejecuta ambos desde la carpeta de finanzas del usuario (donde está `.memory/`). Toda salida es JSON.

## Reglas (no negociables)

1. **Nunca abras ni leas un PDF.** Solo `mxbank extract` (reglas del skill `mxbank`).
2. Extrae **siempre con la misma llave**: `--pseudonym-key-env MXBANK_KEY`. Sin llave, `FIN import` rechaza el JSON
   (los ids cambiarían y se duplicarían movimientos). Si la variable no existe, pide al usuario que la defina;
   nunca la pidas en la conversación ni la escribas en un archivo.
3. Los montos en la memoria son **enteros en centavos** (`MXN_cent`). Convierte al presentar: 123456 → $1,234.56.
4. **No inventes** qué es un comercio, contraparte (`PERSONA_…`) o movimiento desconocido: pregunta.
5. Las **categorías las aprueba el usuario**. Tú propones; él decide. Guarda sus palabras literales con `--source`.
6. Informas y organizas; **no eres asesor financiero** ni ejecutas pagos o transferencias.
7. Reportes con datos reales: en la conversación o en `reportes/` (ignorada por git). No los publiques sin que lo pida.

## Carpeta de finanzas

```text
mis-finanzas/            ← el usuario la elige; es un repo git o una carpeta normal
  .memory/               ← la memoria (se crea sola, ignorada por git)
  estados/               ← PDFs y JSON de mxbank (ignorada por git)
  reportes/              ← salidas locales (ignorada por git)
```

## 1. Arranque

1. `MEM brief --format text` (o el que inyectó el hook). Muestra pagos pendientes, decisiones y la actividad
   de importación en una línea.
2. Si no hay memoria: sigue "Start the memory" del skill `project-memory` (pide nombre y clave `person:<id>`),
   y después `FIN setup --by person:<id>`. `setup` carga 12 categorías principales, reglas por tipo de
   movimiento, recetas y declara `transaction` como tipo de alto volumen. Se puede repetir sin duplicar.
3. Si hay pagos pendientes (`payment_due`) con fecha próxima o vencida, menciónalos primero.

## 2. Importar estados de cuenta

```bash
mxbank extract estados/2026-09/ --ndjson --pseudonym-key-env MXBANK_KEY > estados/2026-09.jsonl
FIN import estados/2026-09.jsonl --by person:<id>
```

- Acepta JSON o NDJSON, varios archivos, en cualquier orden. Reimportar no duplica (`transactions_existing`).
- Si `mxbank` sale con código distinto de 0, sigue la tabla de su skill y no importes.
- La salida trae por estado: `reconciled`, movimientos nuevos/existentes, `warnings`, `payments_settled`
  (pagos de tarjeta encontrados en el estado siguiente) y, al final, `to_classify` y `pending`.
- Si `reconciled` no es `true`, avisa que las cifras pueden estar incompletas.

Después de importar, presenta: cuántos movimientos nuevos por cuenta, si concilian, pagos pendientes y la
propuesta de categorías (sección 3).

## 3. Categorías: base fija, detalle dinámico

**Fijas (no crees otras principales sin que el usuario lo pida):** Housing/Vivienda · Food/Alimentación ·
Transport/Transporte · Health/Salud · Education/Educación · Entertainment/Entretenimiento ·
Subscriptions/Suscripciones · Personal shopping/Compras personales · Financial costs/Costos financieros ·
Income/Ingresos · Internal movements/Movimientos internos · Other/Otros. Cada una trae `<grupo>/general`.

**Dinámicas:** subcategorías (`category:food/restaurants`) y reglas. La categoría **no** se guarda en el
movimiento: cada movimiento apunta (`classified_by`) a su comercio (`merchant:…`), contraparte
(`counterparty:PERSONA_…`) o tipo (`kind:…`), y esa entidad tiene la regla `categorized_as`. Cambiar una
regla recategoriza todo su historial sin reescribir nada.

Flujo después de cada importación:
1. Toma `to_classify` (los que aún no tienen regla, ordenados por monto).
2. Revisa las categorías existentes: `MEM list --entity-type category --column key --column name`.
   Prefiere una existente; crea subcategoría solo si ninguna sirve.
3. Propón **todo junto, en un solo mensaje**, agrupado por categoría, con "Sin clasificar" para lo que no
   reconozcas. Contrapartes (`PERSONA_…`): pregunta qué son ("¿PERSONA_7f3a es tu casero?").
4. Con la aprobación:
   ```bash
   FIN add-category --key category:food/restaurants --name Restaurants --alias Restaurantes --by person:<id>
   FIN categorize --rule merchant:toks=category:food/restaurants --rule counterparty:PERSONA_7f3a=category:housing/general \
       --by person:<id> --source "<palabras literales del usuario>"
   ```
   Las reglas siempre apuntan a una **subcategoría** (`<grupo>/<sub>` o `<grupo>/general`).
5. **Excepción para un solo movimiento** ("lo de Amazon fue un regalo"):
   `FIN recategorize TX_… --to category:other/general --reason "regalo" --by person:<id>`.
   Reemplaza la excepción anterior de ese movimiento, si había.

Reglas por tipo que ya trae `setup` (el usuario las puede cambiar con `categorize --rule kind:<tipo>=…`):
pagos a tarjeta, traspasos propios, retiros de efectivo y traslados a meses → Movimientos internos;
comisiones, impuestos y pagos de préstamos → Costos financieros; nómina e intereses ganados → Ingresos.
SPEI y transferencias **sin** contraparte, y depósitos en efectivo, quedan sin regla: pregunta.

**Qué no es gasto** (por eso `internal` se excluye de los reportes): el pago a la tarjeta desde débito y su
abono en la tarjeta, traspasos entre cuentas propias, retiros (el gasto real del efectivo se captura aparte)
y los traslados a meses (`ALTA PARA MESES` / `ABONO FINANC.`).

**Compras convertidas a meses después** (aparece `installment_conversion` en la importación): la compra
original cuenta como gasto y también contarían sus parcialidades futuras. Señálalo y propón
`FIN recategorize <TX de la compra original> --to category:internal/installment-conversion` para contar el
gasto mes a mes por sus parcialidades. Confirma con el usuario.

## 4. Capturar gastos en efectivo o sin estado de cuenta

```bash
FIN expense --amount 180 --description "Fonda Doña Mary" --date 2026-09-20 --by person:<id> --source "<sus palabras>"
FIN expense --amount 500 --description "Venta de bici" --income --by person:<id>
```

- Por omisión va a `account:cash`. Con `--classifier merchant:…` usa un comercio existente (búscalo antes con
  `MEM search`); si no, crea uno con la descripción y queda en `to_classify` hasta que tenga regla.
- Repetir la misma captura no duplica; dos gastos idénticos el mismo día necesitan `--nonce 2`.

## 5. Presupuestos

`FIN budget --category category:food/groceries --amount 4000 --month 2026-10 --by person:<id>`

Vale desde ese mes hasta que se cambie (el valor anterior queda en la historia). Puede ir en una
subcategoría o en una principal; en el reporte por categoría principal se suman.

## 6. Preguntas y reportes

| Pregunta | Cómo |
|---|---|
| ¿Cuánto gasté este mes y cómo voy con el presupuesto? | `FIN report --month 2026-09 [--level sub]` |
| Mes contra mes | `MEM recipe run recipe:monthly-cashflow --param start=… --param end=…` |
| Historial de un comercio o persona | `MEM recipe run recipe:classifier-history --param who=merchant:netflix` |
| ¿Qué falta categorizar? | `MEM recipe run recipe:uncategorized` |
| Saldos actuales | `MEM list --entity-type account --column name --column fact:balance --column fact:balance/since` |
| Compras a meses vigentes | `MEM list --entity-type installment_plan --where "fact:pending_balance > 0" --column name --column fact:pending_balance --column fact:installments_paid --column fact:installments_total` |
| Intereses y comisiones de tarjeta | `MEM list --event-type statement_imported --column summary --column attr:interest_charged --column attr:fees_charged` |
| Pagos pendientes | `MEM pending` |

- `FIN report` y las recetas `spending-*` y `monthly-cashflow` resuelven la categoría de cada movimiento como
  `first(link-in:recategorizes/link:to_category | link:classified_by/fact:categorized_as)`: la excepción, si
  hay; si no, la regla. Usa esa misma ruta en consultas propias. Excluyen movimientos internos.
- Para valores con fecha (saldo, presupuesto) en un mes pasado usa `--as-of`. Un valor con vigencia futura
  (presupuesto del mes que viene) no aparece como vigente hasta su fecha.
- `uncategorized` en el reporte es dinero sin regla: resuélvelo antes de sacar conclusiones.
- Para preguntas que se repiten, guarda una receta nueva (skill `project-memory`).

## 7. Pagos de tarjeta

- Cada estado de tarjeta crea un `payment_due` pendiente con el pago para no generar intereses y la fecha
  límite. Al importar el estado siguiente, `FIN import` busca los pagos hechos a tiempo y lo cierra
  (`payment_due_settled`, con `covered` y `shortfall`). Si `covered` es `false`, avisa que habrá intereses.
- Si el usuario dice que ya pagó antes de tener el estado siguiente, registra un evento que lo resuelva:
  `MEM write` con un evento `payment_reported` (`links: [{"predicate": "resolves", "event": "DUE_ST_…"}]`,
  `source` con sus palabras). El estado siguiente lo confirmará.

## 8. Cierre de mes (cuando el usuario lo pida)

1. Importar los estados del mes de todas las cuentas.
2. Resolver `to_classify` y `recipe:uncategorized`.
3. Preguntar por gastos en efectivo que falten (comparar retiros con lo capturado).
4. `FIN report --month <mes>` y comparación con el mes anterior.
5. Señalar lo accionable: categorías sobre presupuesto, intereses o comisiones pagados, suscripciones nuevas
   o con aumento de precio, pagos de tarjeta no cubiertos.
6. `MEM backup`.

## Presentar resultados

- Pesos con separador de miles y dos decimales. Empieza por ingresos, gasto, neto y lo pendiente.
- Usa los nombres en el idioma del usuario (las categorías tienen alias en español).
- Marca qué es dato y qué es estimación. Si algo no cuadra, dilo; no ajustes cifras.
