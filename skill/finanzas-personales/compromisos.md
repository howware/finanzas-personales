# Módulo compromisos (opcional)

Ver hacia adelante: **presupuesto, real y pronóstico**, como el *revenue management* de un hotel, aplicado a las
deudas. Qué ya está comprometido (créditos, compras a meses, pagos con tarjeta), cómo vas a terminar la semana, el
mes o el año, y un plan para liquidar créditos que se ajusta sobre la marcha.

Léelo solo si el módulo está activo (`MEM list --entity-type module --column key --column fact:module_active`
muestra `module:compromisos` en `true`) o si la persona pide activarlo. Las reglas de [SKILL.md](SKILL.md) siguen
vigentes; aquí se agregan las del módulo.

`COMP` = `python "<carpeta de este skill>/scripts/compromisos.py"`, desde la carpeta de finanzas, igual que `FIN`.
Toda salida es JSON; los errores y códigos de salida son los de `FIN` (2 entrada inválida, 3 memoria).

## Reglas del módulo

1. **El plan se reajusta, no se rompe.** Cada mes se registra lo que de verdad se pagó: más de lo planeado, solo
   el mínimo, o un atraso. El plan se recalcula desde el saldo real. Muestra sin juicio cómo se movieron las
   fechas de término y propone cómo recuperar el ritmo, si se puede y cuando se pueda. Un mes de mínimo por una
   emergencia (médico, accidente u otra) es parte del plan.
2. **Los mínimos y el colchón van primero.** El abono extra sale solo de lo que sobra después del gasto, los
   pagos exigibles, las compras a meses y lo que falte del colchón. La propuesta puede ser $0.
3. **Las proyecciones son estimaciones.** Di "estimado" en todo saldo o fecha que calcule `COMP`. El saldo oficial
   es el del acreedor: cuando la persona lo tenga, regístralo con `COMP balance` y todo se recalcula desde ahí.
4. **Informas y calculas; no eres asesor financiero.** Avalancha y bola de nieve se presentan como opciones con
   sus números; la persona elige. No recomiendes productos, créditos ni inversiones.
5. **No hay límite de endeudamiento por omisión.** Muestra el porcentaje comprometido; si la persona fija su propio
   límite, guárdalo como regla suya (`MEM remember` con sus palabras) y úsalo en los avisos.
6. **Sin números de crédito ni de contrato.** El crédito se nombra como lo llama la persona («Hipoteca BBVA»). El
   módulo no lee estados de la hipoteca ni de Infonavit: la persona dice el saldo.
7. **Las cascadas se señalan siempre.** Un compromiso que se paga con tarjeta de crédito (Infonavit, un seguro, una
   colegiatura) entra en el pago para no generar intereses de esa tarjeta. Si la tarjeta no se cubre completa,
   la parte no pagada genera intereses a la tasa de la tarjeta. Dilo como dato, con lo que entrega `COMP`, sin
   recomendar dejar de usar la tarjeta.

## Frontera de la exactitud

| Lo hace `COMP` | Lo haces tú |
|---|---|
| Interés mensual (tasa anual / 12 sobre saldo insoluto), amortización, fechas de término | Explicar el resultado y las opciones |
| Ritmo de gasto por día, pronóstico por horizonte, margen y propuesta de abono | Señalar dónde ajustar y proponerlo |
| Conversión del ingreso con el tipo de cambio, y la sensibilidad (`--fx USD=17`) | Preguntar qué tipo de cambio usar |
| Ligar cargos importados a créditos con reglas aprobadas; abrir y cerrar pagos pendientes | Proponer las reglas y confirmar pagos dudosos |
| Recalcular el plan desde el saldo real y los pagos registrados | Mostrar sin juicio cómo se movieron las fechas |
| Detectar cascadas (compromisos en tarjeta, último pago de la tarjeta, intereses) | Explicar el riesgo con esos datos |

Nunca calcules intereses, saldos ni fechas por tu cuenta. Si `COMP` no da un número, dilo.

## Aprobación

| Decisión | Cómo se propone | Cómo se guarda |
|---|---|---|
| Activar el módulo | Solo si la persona lo pide, o al ofrecerlo una vez (ver *Ofrecer*) | `COMP activate --source "<sus palabras>"` |
| Registrar o cambiar un crédito | Repitiendo nombre, tasa, pago, día, saldo y con qué se paga | `COMP credit …` |
| Qué cargo paga qué crédito | Mostrando el comercio o tipo y algunos cargos | `COMP link --classifier … --credit …` |
| Ingreso esperado, tipo de cambio, colchón | Repitiendo monto, moneda y cuentas | `COMP income` · `COMP fx` · `COMP cushion` |
| El plan de liquidación | Comparando avalancha y bola de nieve con el extra propuesto | `COMP plan --strategy … --extra … --save` |

Guarda siempre las palabras literales con `--source`.

## Ofrecer el módulo

Sin activarlo, `finanzas-personales` funciona igual que siempre. Ofrécelo **una sola vez** si en un cierre de mes
o al importar aparecen compras a meses vigentes, intereses cobrados o un pago de tarjeta no cubierto: «¿Quieres ver
cuánto tienes comprometido en los próximos meses y armar un plan para tus créditos?». Si dice que no, guarda la
decisión con `MEM remember` y no vuelvas a ofrecerlo.

## 1. Activar

1. `COMP activate --by person:<id> --source "<sus palabras>"`. Se puede repetir sin duplicar.
2. Pregunta, en un solo mensaje: qué créditos tiene (tipo, acreedor, tasa si la sabe, pago mensual, día de pago,
   saldo y su fecha, con qué cuenta se paga y si acepta abonos a capital); de qué vive (fuentes de ingreso, moneda,
   si es un monto esperado o variable); y si quiere un colchón, de cuánto y en qué cuentas.
3. Registra lo aprobado (secciones 2 y 3) y termina con `COMP forecast --horizon month`.

## 2. Créditos

```bash
COMP credit --name "Hipoteca BBVA" --kind mortgage --lender BBVA --rate 12 --payment 12000 --charges 500 \
    --day 5 --balance 900000 --balance-date 2026-09-30 --paid-with account:ACC_… --prepayment yes --by person:<id>
COMP credit --name "Préstamo de mi hermano" --kind other --payment 2000 --day 15 --remaining 10 --by person:<id>
COMP credit --key credit:hipoteca-bbva --update --payment 12500 --by person:<id>
COMP balance --credit credit:hipoteca-bbva --amount 884312.50 --date 2026-10-31 --by person:<id>
```

- `--payment` es el pago mensual exigible completo; `--charges` es la parte de seguros y comisiones que trae
  dentro (si la persona la sabe), para que el interés y el capital salgan bien.
- **Sin tasa** (no la recuerda, préstamo informal): se lleva como calendario con `--remaining`; no se le
  calculan intereses ni abonos a capital. Dilo.
- Busca la cuenta con `MEM list --entity-type account --column key --column name --column fact:account_product`.
  Si el crédito se descuenta de nómina (Infonavit o Fonacot de un asalariado), no hay cuenta: omite `--paid-with`
  y registra los pagos con `COMP pay` cuando la persona los confirme.
- Solo créditos con tasa fija en pesos. Un crédito en VSM o con tasa variable: dilo y no lo simules (fuera de esta
  versión).

## 3. Pagos de los créditos

1. Después de cada `FIN import`, corre `COMP sync`. Crea un pago pendiente (`payment_due`) por crédito y mes, que
   `MEM brief` y `MEM pending` muestran como los de la tarjeta; liga los cargos de las reglas aprobadas y cierra
   los pagos que ya se pueden verificar.
2. **Primera vez:** busca en los movimientos el cargo de cada crédito (`recipe:classifier-history`, el comercio del
   acreedor, `kind:loan_payment`) y propón la regla: «¿El cargo de INFONAVIT en tu tarjeta es el pago de la
   hipoteca Infonavit?». Con el sí: `COMP link --classifier merchant:infonavit --credit credit:hipoteca-infonavit`.
3. La salida de `sync` trae:
   - `dues_settled`: pagos cerrados, con `covered`, `shortfall`, `extra` (abono arriba del exigible) y
     `arrears_paid` (lo que cubrió un atraso anterior).
   - `overdue_unverified`: pagos con fecha pasada que aún no se pueden ver (sin regla, o el estado de esa cuenta
     no ha llegado). **Pregunta** si ya se pagó; nunca lo des por no pagado.
4. «Ya pagué la hipoteca», o un pago por otra vía: `COMP pay --credit … --amount … --date …`. Si el periodo ya se
   había cerrado con faltante, se vuelve a cerrar con el pago nuevo (el cierre anterior queda anulado, no borrado).

## 4. Ingreso, tipo de cambio y colchón

```bash
COMP income --name "Cliente USA" --amount 3000 --currency USD --frequency monthly --mode expected --by person:<id>
COMP income --name "Honorarios" --mode average --months 6 --by person:<id>
COMP fx --currency USD --rate 18.50 --by person:<id>
COMP cushion --target 60000 --account account:ACC_… --by person:<id>
```

- `expected`: un monto que la persona espera. `average`: el promedio de lo que la categoría Ingresos registró en
  los últimos meses (para ingreso irregular).
- El tipo de cambio es el de referencia que elige la persona. Para «¿y si el dólar baja?», `COMP forecast --fx USD=17`
  sin guardar nada.
- El colchón es la suma de los saldos de sus cuentas en el último estado. Si esas cuentas también se usan para el
  gasto diario, dilo al presentarlo.

## 5. Pronóstico

`COMP forecast --horizon week|month|quarter|semester|year [--fx USD=…]`

| Horizonte | Qué responde | Qué mirar en la salida |
|---|---|---|
| `week` (lunes a domingo) | ¿Voy bien esta semana? | `actual`, `forecast`, `budget`, `dues_this_week` |
| `month` | ¿Cómo cierro el mes? ¿Cuánto puedo abonar? | `months[0]`, `available_for_extra` |
| `quarter`, `semester` | ¿Cuánto tengo comprometido? | `credit_payments`, `installments`, `margin` por mes |
| `year` | ¿Qué se libera y cuándo termino? | `msi_ending`, `credits_ending`, `cumulative` |

- **Ritmo** (`pace.daily`): gasto promedio por día de los últimos 90 días con datos, sin movimientos internos,
  ingresos, pagos de créditos ni parcialidades a meses (esos van aparte como compromisos). Si
  `uncategorized_in_pace` no es $0, resuelve categorías antes de concluir.
- **Pronóstico del mes** = gasto real a la fecha + ritmo × días que faltan. `variance_vs_budget` es presupuesto
  menos pronóstico (negativo: vas arriba).
- **Margen** = ingreso esperado − gasto pronosticado − pagos exigibles − compras a meses. `planned_extra` y
  `margin_after_plan` usan el plan guardado.
- `data_through`: hasta dónde hay movimientos importados. Lo posterior es estimado; dilo.
- Presenta el horizonte como la tabla del hotel: presupuesto, pronóstico y diferencia; luego margen y lo
  comprometido. Termina con lo accionable: categorías arriba del presupuesto, compras a meses que se liberan,
  cascadas.

## 6. Plan de liquidación

1. Propón el abono extra con `available_for_extra` del pronóstico del mes («este mes podrías abonar hasta $X»).
   La persona decide el monto; puede ser menos o $0.
2. `COMP plan --extra <monto>` compara **avalancha** (el extra va al crédito de tasa más alta: menos intereses) y
   **bola de nieve** (al de menor saldo: libera antes un pago completo), contra pagar solo el mínimo: fecha libre de
   deudas, intereses totales, intereses ahorrados y meses ganados por crédito. Cuando un crédito termina, su pago
   se suma al extra del siguiente.
3. Con la elección: `COMP plan --strategy avalanche --extra 3000 --save --source "<sus palabras>"`. Cada versión
   queda guardada; el plan anterior no se borra.
4. Los créditos sin abono a capital permitido (`--prepayment no`) o sin tasa no reciben extra; `not_simulated` lista
   los que no se pudieron simular.

## 7. Revisión del plan (en el cierre de mes, o cuando la persona lo pida)

1. `COMP sync` y `COMP review --month <mes>`.
2. Por crédito, `status`: `above_plan` (pagó más), `as_planned`, `minimum_or_partial_extra` (el mínimo o parte del
   extra), `below_minimum` (menos que el exigible) o `no_payment_found` (pregunta antes de concluir).
3. `recalculated`: fecha de término planeada contra la nueva y `months_later` (negativo: se adelantó).
4. Preséntalo según la regla 1: qué pasó, cómo se movieron las fechas, y una propuesta para el mes siguiente con el
   pronóstico nuevo (`COMP forecast`). Si la persona quiere cambiar estrategia o extra, guarda una versión nueva.

## 8. Cascadas

`COMP cascades` (también viene en `forecast`): por tarjeta, los créditos que se le cargan, las compras a meses, el
total comprometido al mes en esa tarjeta, el último pago de la tarjeta (`covered`, `shortfall`) y los intereses
del último estado.

- Si `at_risk` es `true` (el último pago no cubrió el pago para no generar intereses), dilo primero: qué
  compromisos quedaron financiados a la tasa de la tarjeta y los intereses que trajo el estado.
- Aunque no haya riesgo, al activar el módulo y en la primera revisión explica una vez que esos pagos dependen de
  cubrir la tarjeta completa.

## Al cierre de mes (sección 8 de SKILL.md)

Con el módulo activo, después del reporte del mes: `COMP sync`, `COMP review --month <mes>` si hay plan,
`COMP forecast --horizon month` para el mes que empieza y las cascadas en riesgo. Una propuesta concreta para el
mes siguiente, que la persona aprueba.
