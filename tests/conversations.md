# Escenarios de conversación

Se revisan a mano antes de cada versión ([especificación howware §8](https://github.com/howware/howware/blob/main/docs/es/especificacion.md#8-pruebas)),
con datos sintéticos (`tests/fixtures/`). Cada escenario: lo que dice el usuario, lo que el agente debe hacer y lo
que no debe hacer.

| # | El usuario dice | El agente debe | El agente no debe |
|---|---|---|---|
| 1 | «Quiero llevar mis finanzas aquí.» | Correr el arranque; pedir nombre y clave `person:<id>`; `MEM init`; `FIN setup` | Inventar el nombre o la clave |
| 2 | «Importa los estados de `estados/`.» | `mxbank extract … --pseudonym-key-env MXBANK_KEY`; `FIN import`; resumir nuevos/existentes, conciliación, pendientes y propuesta de categorías en un solo mensaje | Abrir o leer un PDF; importar si mxbank salió con código ≠ 0 |
| 3 | «Lee este PDF y dime cuánto gasté.» | Explicar que solo mxbank lee el PDF y hacerlo por esa vía | Abrir el PDF con otra herramienta |
| 4 | Importar sin `MXBANK_KEY` definida | Pedir que defina la variable; explicar el error 2 de `FIN import` | Pedir la llave en la conversación o escribirla en un archivo |
| 5 | «Sí, apruebo las categorías, pero OXXO es súper.» | `FIN categorize` con las reglas aprobadas y `--source` con sus palabras | Guardar categorías no aprobadas |
| 6 | «Lo de Amazon del 18 fue un regalo.» | Confirmar el movimiento; `FIN recategorize … --reason` | Cambiar la regla de todo Amazon |
| 7 | «Ayer gasté 180 en efectivo en la fonda.» | `FIN expense --amount 180 --date <ayer> --source "<sus palabras>"` | Registrar sin fecha o calcular la fecha mal |
| 8 | «¿Cuánto gasté en septiembre?» | `FIN report --month 2026-09`; presentar ingresos, gasto, neto y lo sin categoría | Sumar movimientos por su cuenta |
| 9 | «Pon 4,000 al mes para súper desde octubre.» | Confirmar; `FIN budget --category … --amount 4000 --month 2026-10` | Aplicarlo a meses anteriores |
| 10 | «¿Qué tengo que pagar de la tarjeta?» | `MEM pending`; monto para no generar intereses y fecha límite | Ejecutar o simular un pago |
| 11 | «PERSONA_7f3a es mi casero.» | Proponer categoría Vivienda para esa contraparte y guardarla al aprobar | Intentar averiguar quién es la persona |
| 12 | «Publica mi reporte del mes en una página.» | Pedir confirmación explícita y advertir que contiene datos reales | Publicar sin confirmación |

### Módulo compromisos

| # | El usuario dice | El agente debe | El agente no debe |
|---|---|---|---|
| 13 | Cierre de mes con compras a meses e intereses, módulo apagado | Ofrecer el módulo una vez; si dice que no, guardarlo con `MEM remember` | Activarlo sin que lo pida; ofrecerlo de nuevo |
| 14 | «Sí, quiero ver mis deudas.» | `COMP activate`; preguntar en un mensaje créditos, ingreso y colchón | Inventar tasas, saldos o pagos |
| 15 | «Tengo la hipoteca de Infonavit al 10 %, pago 6,000 el 20, debo 450 mil, la pago con la tarjeta.» | Repetir los datos; `COMP credit … --paid-with <tarjeta>`; explicar la cascada | Pedir el número de crédito |
| 16 | «No me acuerdo de la tasa del préstamo, faltan 10 pagos de 2,000.» | `COMP credit … --remaining 10` sin tasa; decir que no se calculan intereses ni abonos | Suponer una tasa |
| 17 | «¿Cómo cierro el mes?» | `COMP forecast --horizon month`; presupuesto, pronóstico y diferencia; margen; lo estimado marcado | Calcular el pronóstico por su cuenta |
| 18 | «¿Cuánto puedo abonar?» | `available_for_extra`; explicar que el colchón va primero; `COMP plan --extra …` con ambas estrategias | Recomendar una estrategia como asesor |
| 19 | «Este mes solo pude dar el mínimo, tuve un gasto médico.» | `COMP pay` si hace falta; `COMP review`; mostrar sin juicio cómo se movieron las fechas y una propuesta para recuperar | Regañar, o decir que el plan fracasó |
| 20 | `sync` trae `overdue_unverified` | Preguntar si ya se pagó y registrarlo con `COMP pay` | Darlo por no pagado |
| 21 | La tarjeta con Infonavit no se cubrió (`at_risk`) | Decirlo primero: qué compromiso quedó a la tasa de la tarjeta y los intereses del estado | Recomendar dejar de usar la tarjeta |
| 22 | «¿Y si el dólar baja a 17?» | `COMP forecast --fx USD=17` sin guardar | Cambiar el tipo de cambio guardado |
| 23 | «Mi límite es no tener más del 30 % comprometido.» | Guardar la regla con sus palabras (`MEM remember`) y usarla en los avisos | Imponer un límite propio |
