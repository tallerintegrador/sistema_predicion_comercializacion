"""Canal de entrada **Excel** — otra puerta al MISMO contrato (Fase 3.3).

Excel es **solo una puerta**, no lógica nueva. Este paquete:

- **`esquema_excel`** — define, por dominio, qué hojas y columnas tiene la plantilla,
  derivando los nombres y tipos de los **mismos modelos Pydantic** del contrato (para
  que plantilla y lector no se desincronicen nunca).
- **`plantilla`** — genera el ``.xlsx`` descargable a partir de esa definición
  (encabezados en inglés, una fila de ejemplo y una hoja de instrucciones en español).
- **`lector`** — lee un ``.xlsx`` subido, **convierte los tipos explícitamente** al
  contrato (necesario porque la validación es ``strict``), arma la misma petición que
  enviaría el JSON y la valida con los **mismos modelos**; los errores citan hoja, fila
  y columna con el mismo cuerpo de error de la API.

El flujo de predicción NO se duplica: tras validar, el router de Excel llama al **mismo
handler** que sirve el JSON.
"""
