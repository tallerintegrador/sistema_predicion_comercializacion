# Sistema Predictivo de Comercializacion (SPC) — EDA

Analisis exploratorio reproducible del dataset **Store Sales - Corporacion Favorita**
(Taller Integrador I). El pipeline lee los CSV crudos, calcula metricas de calidad y
exploracion, genera figuras y **redacta el reporte automaticamente**: no hay cifras
escritas a mano, todo proviene de los calculos ejecutados sobre los archivos locales.

Antes era un unico `eda.py` de ~1700 lineas. Ahora es el paquete modular `spc`,
testeado y con tooling de calidad.

## Estructura

```
src/spc/
  config.py            # Settings (rutas, semilla, estilo de figuras) inmutable
  logging_setup.py     # logging configurable
  io/                  # carga de CSV (schemas + loaders) y escritura de artefactos
  quality/             # perfilado y chequeos de calidad
  features/            # integracion de fuentes y dataset analitico
  analysis/            # objetivo, univariado, temporal, relacional, correlacion,
                       #   clasificacion, clustering
  viz/                 # estilo unificado + figuras
  reporting/           # formatters, reporte Markdown y notebook
  pipeline.py          # run_pipeline() orquesta todo + CLI
scripts/run_eda.py     # entry point de linea de comandos
tests/                 # pytest sobre data sintetica
eda.py                 # shim: python eda.py / import eda; eda.main()
```

Flujo (tareas A–J del enunciado): carga → perfilado → calidad → variable objetivo →
univariado → temporal → integracion → bivariado/correlaciones → aptitud
(regresion/clasificacion/clustering).

## Requisitos previos

Colocar los 7 CSV del dataset en `data/raw/`:
`train.csv`, `test.csv`, `stores.csv`, `transactions.csv`, `oil.csv`,
`holidays_events.csv`, `sample_submission.csv`.

## Instalacion

```powershell
python -m venv venv
venv\Scripts\python -m pip install -e .[dev]
```

(`pip install -e .` sin `[dev]` instala solo lo necesario para ejecutar el EDA.)

## Ejecutar el EDA

```powershell
venv\Scripts\python scripts\run_eda.py        # genera todo
venv\Scripts\python scripts\run_eda.py -v     # logging DEBUG
venv\Scripts\python scripts\run_eda.py --no-notebook
# tambien: venv\Scripts\python eda.py   (shim de compatibilidad)
```

Desde Python:

```python
import spc
resumen = spc.run_pipeline()
```

## Artefactos generados

- `data/processed/*.csv` y `*.json` — tablas intermedias y resumenes.
- `figures/01..19_*.png` — figuras con estilo unificado.
- `reporte_eda.md` — reporte redactado.
- `notebooks/eda.ipynb` — notebook reproducible que recorre el flujo.

## Figuras: que se corrigio

Las figuras se rehicieron para que cada una sustente correctamente su afirmacion:

- **Estacionalidad mensual (04):** ahora es un **indice estacional** (media del mes /
  media diaria de su anio, promediada entre anios). El promedio crudo anterior mezclaba
  tendencia con estacionalidad (Sep–Dic no tienen datos de 2017, el anio de mayor nivel).
- **Petroleo vs ventas (09):** coloreado por anio, porque la correlacion negativa global
  es en gran parte espuria por la tendencia temporal.
- **Correlaciones (10):** triangulo superior enmascarado (mitad redundante).
- **Promocion vs ventas (07):** promedio directo de `sales` por bin de `onpromotion`.
- **Transacciones vs ventas (08):** linea de tendencia para leer la relacion.
- **Resto:** tema, paleta, tamanos y dpi unificados; acentos correctos; etiquetas de
  valor donde aportan.

## Calidad

```powershell
venv\Scripts\python -m pytest        # tests
venv\Scripts\ruff check src tests    # lint
venv\Scripts\black --check src tests # formato
venv\Scripts\mypy src                # tipos
```
