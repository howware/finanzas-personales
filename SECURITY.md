# Seguridad y privacidad

## Reportar un problema

Si encuentras una vulnerabilidad, o un caso en el que el skill o `fin.py` **exponen datos financieros o
personales** (por ejemplo, el agente lee un PDF, algo se publica sin permiso o un dato real termina en un
archivo versionado), repórtalo **de forma privada**:

1. Ve a **Security → Report a vulnerability** del repositorio, o abre
   https://github.com/howware/finanzas-personales/security/advisories/new.
2. Describe el problema **sin incluir datos reales**: versiones (`python fin.py --version`,
   `mxbank version`, `memory.py --version`), el comando o la conversación que lo produjo con montos y nombres
   reemplazados, y qué se expuso (tipo de dato, nunca el valor).

**Nunca publiques** estados de cuenta, JSON de mxbank, memorias (`.memory/`), reportes ni capturas con datos
reales en issues, pull requests o discusiones públicas.

Si el problema está en la lectura del PDF o en la anonimización, repórtalo en
[mxbank](https://github.com/howware/mx-bank-statement-reader/security/advisories/new); si está en el
almacenamiento, en [Long-Term Memory for AI](https://github.com/howware/long-term-memory-for-AI).

## Qué esperar

Es un proyecto personal mantenido en tiempo libre: se responde en cuanto sea posible, sin un plazo garantizado.
Las exposiciones de datos tienen prioridad sobre cualquier otro cambio.

## Versiones con soporte

Solo la versión más reciente publicada en `main`.

Ver también el [aviso legal y advertencias de uso](AVISO-LEGAL.md).
