# 03 · Módulo compromisos

Diseño del módulo opcional de la versión 0.4.0: créditos, pronóstico y plan de liquidación de deudas.

## 1. De dónde viene

La idea salió de cómo un hotel lleva su *revenue management*: un **presupuesto** al empezar el año, un
**pronóstico** que se actualiza durante el mes con lo que ya está reservado (*on the books*) y el ritmo de
reservas (*pickup*), y la **diferencia** detectada antes de que termine el mes, cuando todavía se puede corregir.
La fórmula del hotel (ingreso = tarifa promedio × noches vendidas) tiene una versión personal:

| Hotel | Persona |
|---|---|
| Tarifa promedio por noche (ADR) | Gasto promedio por día (`pace.daily`) |
| Noches vendidas | Días del mes, o los que faltan |
| *On the books* | Compromisos firmados: créditos, compras a meses, pagos con tarjeta |
| *Pickup* | El gasto real que se va sumando contra el presupuesto |
| Presupuesto · pronóstico · diferencia | Igual, por semana, mes, trimestre, semestre y año |

`finanzas-personales` ya ve hacia atrás (¿qué pasó?). El módulo ve hacia adelante (¿cómo voy a terminar y qué ya
tengo comprometido?) y ayuda a salir de deudas sin endeudarse más.

## 2. Lo que dijo el dueño (entrevista de `howware-builder`)

- **Horizontes:** corto, mediano y largo plazo: semanal, mensual, trimestral, semestral y anual.
- **Deudas:** también las que no salen en el estado de cuenta. En su caso, tarjetas de crédito y dos hipotecas
  (una bancaria, una de Infonavit en pesos) con tasas conocidas y abonos a capital sin penalización.
- **Ingreso:** esperado; el principal depende del tipo de cambio pero en promedio es estable. Otras personas
  tendrán ingreso fijo en pesos o irregular.
- **Límite:** no tenía uno; el concepto es nuevo. El módulo no impone tope.
- **Compras a meses:** ya son "un plan en curso"; importa cuándo se liberan.
- **Lo central:** dónde ajustar para no endeudarse más, un plan de liquidación y ajustarlo sobre la marcha.
- **Lo que más dolería:** un pago olvidado y quedarse sin dinero. El colchón, "excelente".
- **La regla del dueño:** a veces, por eventualidades (médico, accidente), solo se paga el mínimo o se atrasa; el
  plan se reajusta en ambos sentidos. Quedó como la regla 1 del módulo.
- **Las cascadas:** el dueño paga Infonavit con tarjeta de crédito por comodidad. Si la tarjeta no se cubre
  completa, ese pago de hipoteca pasa a la tasa de la tarjeta. Pidió que la herramienta detecte ese tipo de riesgo.
- **Opcional:** no a todos les interesa; vive dentro de `finanzas-personales` como módulo que se activa.

## 3. Decisiones

| # | Decisión | Motivo |
|---|---|---|
| C1 | Módulo opcional dentro de `finanzas-personales`, no un howware aparte | Presupuestos, categorías, compras a meses y pagos de tarjeta ya viven aquí; un howware aparte tendría que reimplementarlos |
| C2 | Protocolo propio (`compromisos.md`) y herramienta propia (`compromisos.py`), activación explícita guardada en la memoria (`module:compromisos`) | Quien no lo usa no carga ni ejecuta nada nuevo; cada pieza sigue siendo pequeña |
| C3 | `compromisos.py` usa la conexión a la memoria y las utilidades de `fin.py` | Un solo cliente de la memoria; mismos centavos, fechas y errores |
| C4 | Interés mensual = tasa anual / 12 sobre saldo insoluto, al centavo; el pago incluye seguros y comisiones (`--charges`) | Así calculan los créditos hipotecarios a tasa fija en pesos; es una estimación y se dice |
| C5 | El saldo real que da el acreedor (`balance`) es el ancla; entre anclas se estima con los pagos registrados | El dueño ve su saldo en el portal; el módulo no lee estados de hipoteca |
| C6 | Un mes sin datos de pago se supone pagado con el exigible mientras no haya estado que lo verifique | Nunca dar por no pagado lo que todavía no se puede ver |
| C7 | Los cargos se ligan a un crédito con una regla en el clasificador (`pays_credit`), como las categorías | Una aprobación sirve para todo el historial |
| C8 | Un pago pendiente (`payment_due`) por crédito y mes, cerrado por `credit_due_settled`; si llega un pago tarde, el cierre se anula y se rehace | El arranque ya muestra los `payment_due`; la memoria es solo de agregado |
| C9 | Sin regla de ligado, un crédito solo se cierra con pagos que dice la persona | Evita marcar como no pagado un crédito cuyos cargos no se buscan |
| C10 | Ritmo de gasto sin internos, ingresos, pagos de créditos ni parcialidades a meses | Esos van como compromisos; contarlos en el ritmo los duplicaría |
| C11 | El colchón se completa antes del abono extra (`available_for_extra` = margen − lo que falta del colchón) | La regla del dueño: no quedarse sin dinero |
| C12 | Avalancha y bola de nieve siempre lado a lado contra "solo el mínimo"; el pago de un crédito terminado se suma al extra | La persona elige con números; no es asesoría |
| C13 | Cada plan aprobado es un evento `debt_plan` con sus fechas de término y sus primeros 24 meses | La revisión compara contra lo que se planeó, no contra el plan de hoy |
| C14 | Las cascadas cruzan los créditos pagados con tarjeta, las compras a meses de esa tarjeta y su último pago | El riesgo del dueño, convertido en dato |
| C15 | Ingreso por fuente con moneda y modo (`expected` o `average`); tipo de cambio de referencia como texto decimal | Sin flotantes; sensibilidad con `--fx` sin guardar nada |

## 4. Modelo en la memoria

| Registro | Tipo | Datos |
|---|---|---|
| `module:compromisos` | entidad `module` | `module_active` |
| `credit:<nombre>` | entidad `credit` | `credit_kind`, `lender`, `annual_rate_bp`, `scheduled_payment`, `included_charges`, `payment_day`, `remaining_payments`, `principal_balance` (con fecha), `paid_with`, `prepayment_allowed`, `tracking_since` |
| comercio, contraparte o tipo | (los de finanzas) | `pays_credit` → crédito |
| `CPAY_…` | evento `credit_payment` | `credit_payment_amount`, `entry_source`; `for_credit`, `from_transaction` |
| `DUE_<crédito>_<mes>` | evento `payment_due` (pendiente) | `payment_due_date`, `scheduled_payment`; `for_credit` |
| `PAID_DUE_…` | evento `credit_due_settled` | `paid_amount`, `shortfall`, `covered`, `extra_payment`, `arrears_paid`; `resolves` |
| `PLAN_<n>` | evento `debt_plan` | `strategy`, `extra_monthly`, `plan_detail_text`; `covers_credit` |
| `income:<nombre>` | entidad `income_source` | `income_amount` (centavos de su moneda), `income_currency`, `income_frequency`, `income_mode`, `average_months` |
| `currency:usd` | entidad `currency` | `fx_rate_text` |
| `cushion:main` | entidad `cushion` | `cushion_target`, `held_in` |

Los predicados están en `seed.json` (`compromisos`, semilla 3); `activate` los declara. `fin.py setup` no cambia.

## 5. Fuera de esta versión

- Créditos en VSM o UMA, o con tasa variable.
- Simular una compra nueva a meses antes de hacerla.
- Avisos fuera de la conversación (programados).
- Leer estados de hipoteca o de Infonavit con un adaptador.
- Inversiones y patrimonio neto.
- Detectar cargos recurrentes en tarjeta (seguros, colegiaturas) como cascadas sin registrarlos como crédito.

## 6. Limitaciones conocidas

- El cálculo puede diferir del acreedor por conteo de días, redondeo, seguros que cambian o el orden en que aplica
  un abono. El saldo real lo corrige en cuanto se registra.
- Un pago hecho después de la fecha límite cuenta para el periodo siguiente, primero cubriendo el faltante
  (`arrears_paid`).
- El ritmo usa 90 días con datos; con poco historial (`days_used` bajo) el pronóstico es menos confiable.
- "Módulo opcional" no es todavía un concepto de la especificación howware; si funciona aquí, se puede proponer.
