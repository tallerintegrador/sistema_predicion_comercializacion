# ADR-0028 — Catálogo de 30 consultas predefinidas (motor v3) y contrato en inglés

- **Estado:** Aceptado
- **Fecha:** 2026-07-03
- **Rama:** `feature/entrega-final`
- **Relacionado:** [ADR-0024](0024-rediseno-3x3-sklearn-sintetico.md) /
  [ADR-0025](0025-mejoras-modelos-variedad-objetivos-clustering.md) (motor 3×3 que esto
  extiende), [ADR-0018](0018-catalogo-tipologias-dimensiones.md) (catálogo declarativo),
  [ADR-0026](0026-retiro-motor-congelado-migracion-frontend-v2.md) (migración de frontend)

## Contexto

El docente pidió un conjunto **fijo y explicable** de consultas por módulo: **10 por módulo
(30 total)**, con distribución **4 regresión + 3 clasificación + 3 clustering**, cada una con
su pregunta de negocio, columnas de entrada FIJAS y modelos candidatos, agnóstica al rubro.
El motor 3×3 (ADR-0024/0025) resolvía "tres modelos por dominio" pero no un catálogo de
consultas nombradas. Además, la salida debía separar el **resultado** (vista principal) de la
**competencia de modelos** (solo detalle técnico), y las **regresiones** debían predecir un
número desde OTROS factores (no del tiempo), reservando la serie temporal a una única sección
de Tendencia.

## Decisión

Se introduce el **motor de catálogo v3**: una **fuente única de verdad declarativa**
(`src/spc/catalogo/consultas.yaml`) con las 30 consultas, ejecutada por un motor genérico
(`motor_catalogo.py`) y expuesta en `/v3/{modulo}`.

- **Catálogo declarativo:** cada consulta declara `tipo`, `pregunta`, `objetivo`,
  `columnas_entrada` (fijas), `modelos_candidatos`, `metrica_seleccion`, derivación de
  etiqueta (percentil / umbral / regla determinística) y notas anti-fuga. Sin hard-codear en
  el motor: umbrales, columnas, ganador y unidades se leen del catálogo/metadata.
- **Una plantilla por módulo → 10 reportes automáticos:** `POST /v3/{modulo}` corre las 10
  consultas (4R → 3C → 3K) y devuelve 10 reportes + un bloque de Tendencia. No hay selector.
- **Validación temporal honesta:** train/valid/test por fecha; selección del ganador en
  VALID; métrica mostrada al usuario = TEST (evaluada una vez). Clustering sin partición.
- **Umbrales no bloqueantes:** siempre se reporta la métrica; si es baja, se advierte con
  lenguaje honesto ("Señal débil…"), pero nunca falla ni se oculta. El fallo de UNA consulta
  se degrada con aviso y no tumba el módulo (nunca un 500).
- **Competencia:** la tabla comparativa de candidatos vive SOLO en "detalle técnico"; la
  vista principal muestra únicamente el resultado.
- **Contrato en inglés:** las **claves del cuerpo JSON** y el **enum `type`**
  (`regression`/`classification`/`clustering`) están en inglés (requisito del docente). Se
  mantienen en español los **valores de negocio** (preguntas, avisos, etiquetas legibles) y
  los **identificadores de datos del cliente**: las columnas de la plantilla (`fecha`,
  `unidades_vendidas`, …) y los valores de módulo en la ruta (`/v3/ventas|compras|almacen`),
  porque son los datos reales del PYME y los 5 datasets de ejemplo.

### Anti-fuga (decisiones de esta entrega)

- El motor construye las features **solo** desde `columnas_entrada`, excluyendo el objetivo y
  las columnas calculadas (`ingreso`, `costo_total`, `cumplimiento`, `dias_de_cobertura`).
- **ALMACÉN R1/R3/R4:** se **quitaron** `demanda_diaria_promedio` y `rotacion` de las
  features. Su valor del mismo día contiene el consumo del día (corr≈0.91 con `demanda_dia`) y
  el motor no rezaga columnas, así que incluirlas era una casi-copia del objetivo (near-leak).
  Se predice solo desde factores causales conocidos a futuro (categoría, zona, reposición);
  la señal baja y se reporta honesta (como ALM-R2).
- **Etiquetas casi determinísticas:** cuando una clasificación derivada (percentil/umbral/
  regla) sale casi perfecta (≥ 0.98), se añade una **nota técnica honesta** explicando que,
  con esos datos, la etiqueta es casi determinística desde los factores — no es fuga (las
  columnas que la definen están excluidas), pero conviene leerla con cautela.

## Consecuencias

- **A favor:** requisitos del docente cubiertos y trazables; salida honesta y a prueba de
  caídas; contrato limpio y consumible; agnóstico al rubro (verificado con 5 sectores).
- **En contra / deuda:** el motor v3 entrena al vuelo y **no** persiste artefactos (a
  diferencia del reentrenamiento de ADR-0027); varias consultas tienen señal débil (WAPE/F1
  modestos), reportada con honestidad; el clustering sobre pocas entidades (2–3 tiendas/zonas/
  proveedores) es referencial y se avisa como tal.

## Alternativas descartadas

- **Selector de consultas en la UI:** contradice "una plantilla → 10 reportes"; descartado.
- **Contrato en español:** más natural para el equipo, pero incumple el requisito del docente;
  se migró a inglés en la frontera, manteniendo internamente los tipos en español.
- **Inflar métricas con columnas casi-idénticas al objetivo:** descartado por deshonesto;
  se prefiere señal débil reportada que métrica artificialmente perfecta.
