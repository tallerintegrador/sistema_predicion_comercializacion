# Archivo — dataset Corporación Favorita (RETIRADO)

Estos CSV son el dataset **Store Sales – Corporación Favorita** (Kaggle) que el motor de
ML usaba originalmente. Tras la revisión del docente (ver `docs/decisiones/0024-rediseno-3x3-sklearn-sintetico.md`),
el proyecto **abandona Favorita** por dos razones:

1. Era lento (~3M filas) y daba modelos poco precisos para una demo.
2. Sus variables no tenían el sentido de negocio genérico que se pide para PYMEs.

En su lugar, cada dominio (ventas/compras/almacén) usa **datos sintéticos realistas** con
su propio formato (`spc.synthetic`), generados con `scripts/generar_datos_sinteticos.py`.

Se conservan aquí (en vez de borrarse) solo como **referencia histórica**:
- El gran `train.csv` (~3M filas) nunca estuvo versionado (gitignored) y no se incluye.
- El motor agnóstico/retail antiguo (`/sales`, `/purchases`, `/inventory`) y sus artefactos
  congelados siguen vivos temporalmente para no romper el frontend; se retirarán cuando el
  frontend migre al contrato 3×3 (`/v2/...`).

No usar estos archivos para nuevo desarrollo.
