# Changelog

Todos los cambios relevantes. Las versiones siguen [Semantic Versioning](https://semver.org/lang/es/).

## 0.2.0 — howware conforme

- finanzas-personales es el primer [howware](https://howware.org) y cumple la especificación 0.1: manifiesto
  `howware.json` con dependencias y las tres listas de privacidad.
- `fin.py`: errores como `{"ok": false, "error": {"code", "message"}}` con códigos de salida 2 (entrada inválida)
  y 3 (memoria); un archivo ilegible o un JSON corrupto ya no terminan en una traza de Python.
- SKILL.md: secciones "Frontera de la exactitud" (qué hace cada herramienta, códigos de salida) y "Aprobación"
  (qué decide el usuario y cómo se guarda).
- `tests/conversations.md`: 12 escenarios de conversación; `tests/test_howware.py`: pruebas de conformidad.

## 0.1.0 — primera versión pública

- Skill `finanzas-personales` para Claude Code y Codex: protocolo de arranque, importación, categorías,
  efectivo, presupuestos, pagos de tarjeta, reportes y cierre de mes.
- `fin.py` (solo biblioteca estándar): `setup`, `import`, `categorize`, `add-category`, `recategorize`,
  `expense`, `budget` y `report`.
- Importación idempotente y en cualquier orden a partir de los ids estables de mxbank; rechaza JSON generados
  sin llave de seudónimos o con esquema anterior a 1.1.
- Categorías: 12 principales fijas con alias en español; subcategorías y reglas por comercio, contraparte o
  tipo de movimiento creadas conforme se importa. Excepciones por movimiento con
  `first(excepción | regla)`.
- Pagos de tarjeta: pendiente por estado con el pago para no generar intereses; se cierra al importar el
  estado siguiente con los pagos hechos a tiempo.
- Presupuestos mensuales con vigencia; el reporte usa el presupuesto en vigor en cada mes.
- Recetas guardadas en la memoria: gasto por categoría y subcategoría, flujo mensual, excepciones, sin
  categoría, historial por comercio y presupuestos.
- Instalador del skill, guardia de datos privados en CI y sitio del proyecto.
- Requiere mxbank ≥ 0.2.0 y Long-Term Memory for AI ≥ 0.3.0.
