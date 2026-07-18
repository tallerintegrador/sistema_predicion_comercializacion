# Notebooks

Orden sugerido para documentar el experimento:

1. `01_exploracion_crudo.ipynb`: esquema, fechas, duplicados y distribución de clases.
2. `02_aplicacion_smotenc.ipynb`: partición temporal, escalado y remuestreo de TRAIN.
3. `03_validacion_reconstruccion.ipynb`: reglas de negocio, distancias y métricas.

Los notebooks deben leer desde `../crudo/`, escribir resultados temporales fuera de esa
carpeta y usar semilla 42. VALID y TEST nunca deben pasar por `fit_resample`.

