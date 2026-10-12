# Aviso legal y advertencias de uso

*Última revisión: octubre de 2026 · aplica a finanzas-personales v0.1.0 y posteriores.*

Este documento resume, hasta donde sabemos, los límites de responsabilidad y las advertencias de uso del
proyecto. **No es asesoría legal.**

## 1. Software "tal cual", sin garantía

finanzas-personales se distribuye bajo la [Licencia Apache 2.0](LICENSE). Conforme a sus secciones 7 y 8:

- Se entrega **"TAL CUAL" (AS IS), sin garantías** de ningún tipo, expresas o implícitas, incluidas las de
  comerciabilidad, idoneidad para un fin determinado, exactitud o no infracción.
- **En ningún caso el autor ni los contribuidores serán responsables** de daños directos, indirectos,
  incidentales, especiales o consecuentes (incluidas la pérdida de datos, la exposición de información, las
  decisiones financieras o fiscales, los cargos por intereses o comisiones y los pagos omitidos o tardíos)
  derivados del uso o la imposibilidad de uso del software, en la máxima medida que permita la ley aplicable.
- Quien usa la herramienta **asume todos los riesgos** de su uso.

## 2. No es asesoría financiera, fiscal ni legal

La herramienta organiza información y responde preguntas sobre ella; **no recomienda inversiones, créditos ni
decisiones financieras**. Las categorías, totales, comparaciones y conclusiones que tú o un agente de IA
obtengan son responsabilidad de quien los produce y los usa. El agente no es un asesor con licencia.

## 3. Exactitud de los datos

- Los movimientos vienen de [mxbank](https://github.com/howware/mx-bank-statement-reader), que puede contener
  **errores u omisiones**; su conciliación contable reduce ese riesgo, pero no lo elimina.
- Las categorías, presupuestos y reportes dependen de reglas que **propone una IA** y apruebas tú: pueden estar
  mal clasificados. Los recordatorios de pago dependen de que importes tus estados a tiempo.
- **El documento válido es siempre el estado de cuenta original** emitido por el banco. Antes de pagar,
  declarar impuestos o hacer una aclaración, verifica las cifras contra él.

## 4. Privacidad

- Todo se guarda **en tu computadora**: un archivo SQLite sin cifrar dentro de la carpeta que elijas.
  Protégelo como cualquier archivo personal (cifrado de disco, respaldos, permisos).
- La memoria es **solo de agregado**: lo que se registra no se puede borrar desde la herramienta, solo
  corregir o anular. No registres datos que podrías estar obligado a eliminar.
- Cuando usas un agente de IA, lo que el agente lee (movimientos anonimizados, respuestas, tus mensajes) se
  envía al **proveedor de IA** y queda sujeto a sus términos y políticas de privacidad, que el proyecto no
  controla. Aunque no contenga tu nombre ni tus cuentas, puede seguir siendo información personal.

## 5. Uso con datos de otras personas

La herramienta está pensada para las **finanzas propias**. Si la usas con datos de otras personas (clientes,
familiares, empleados), **tú eres responsable** de cumplir la legislación aplicable; en México, entre otras,
la Ley Federal de Protección de Datos Personales en Posesión de los Particulares y su normativa secundaria
(consentimiento expreso para datos financieros, aviso de privacidad, medidas de seguridad y reglas para
transferir datos a terceros como un proveedor de IA). Consulta el
[aviso legal de mxbank](https://github.com/howware/mx-bank-statement-reader/blob/main/AVISO-LEGAL.md).

## 6. Marcas

Los nombres de bancos solo identifican los formatos que mxbank sabe leer. Este proyecto **no está afiliado ni
respaldado** por BBVA México, BanCoppel, Anthropic, OpenAI ni ninguna otra empresa o institución financiera.
Claude Code y Codex son marcas de sus respectivos titulares.
