"""Generacion del notebook reproducible que recorre el flujo del EDA."""

from __future__ import annotations

import nbformat as nbf

from spc.config import Settings


def create_notebook(settings: Settings) -> None:
    """Escribe ``notebooks/eda.ipynb``: ejecuta el pipeline y muestra los artefactos."""
    nb = nbf.v4.new_notebook()
    nb["cells"] = [
        nbf.v4.new_markdown_cell(
            "# EDA - Sistema Predictivo de Comercializacion\n\n"
            "Este notebook ejecuta el flujo reproducible del paquete `spc`. "
            "Metricas, figuras y reporte se generan desde los CSV reales en `data/raw`."
        ),
        nbf.v4.new_markdown_cell(
            "## A. Setup y carga\n"
            "Se posiciona en la raiz del proyecto y ejecuta todo el flujo. "
            "Para regenerar todo, volver a correr `spc.run_pipeline()`."
        ),
        nbf.v4.new_code_cell(
            "import os\n"
            "from pathlib import Path\n"
            "import pandas as pd\n"
            "import spc\n\n"
            "# Ubicar la raiz del proyecto (carpeta que contiene data/raw).\n"
            "root = Path.cwd()\n"
            "if root.name == 'notebooks':\n"
            "    root = root.parent\n"
            "os.chdir(root)\n\n"
            "resultados = spc.run_pipeline()\n"
            "processed = Path('data/processed')\n"
            "figures = Path('figures')"
        ),
        nbf.v4.new_markdown_cell("## B. Perfilado general y calidad (con observaciones)"),
        nbf.v4.new_code_cell("pd.read_csv(processed / 'resumen_perfil_archivos.csv')"),
        nbf.v4.new_markdown_cell("## C. Calidad de datos"),
        nbf.v4.new_code_cell(
            "display(pd.read_csv(processed / 'resumen_nulos_columnas.csv'))\n"
            "pd.read_json(processed / 'resumen_calidad.json', typ='series')"
        ),
        nbf.v4.new_markdown_cell("## D. Variable objetivo `sales`"),
        nbf.v4.new_code_cell(
            "display(pd.read_csv(processed / 'sales_descriptivos.csv'))\n"
            "display(pd.read_csv(processed / 'sales_por_familia.csv').head(10))"
        ),
        nbf.v4.new_markdown_cell("## E. Analisis univariado"),
        nbf.v4.new_code_cell(
            "display(pd.read_csv(processed / 'univariado_categoricas.csv'))\n"
            "display(pd.read_csv(processed / 'univariado_numericas.csv'))"
        ),
        nbf.v4.new_markdown_cell(
            "## F. Analisis temporal (incluye estacionalidad anual e indice estacional)"
        ),
        nbf.v4.new_code_cell(
            "display(pd.read_csv(processed / 'ventas_anuales.csv'))\n"
            "display(pd.read_csv(processed / 'indice_estacional_mes.csv'))\n"
            "display(pd.read_csv(processed / 'efecto_tipo_feriado.csv'))\n"
            "display(pd.read_csv(processed / 'dias_pico_ventas.csv'))"
        ),
        nbf.v4.new_markdown_cell("## G. Analisis bivariado y relacional"),
        nbf.v4.new_code_cell(
            "display(pd.read_csv(processed / 'relacional_promo_flag.csv'))\n"
            "display(pd.read_csv(processed / 'relacional_type_sales.csv'))\n"
            "display(pd.read_csv(processed / 'relacional_cluster_sales.csv').head(10))"
        ),
        nbf.v4.new_markdown_cell("## H. Integracion de fuentes y catalogo de columnas"),
        nbf.v4.new_code_cell(
            "display(pd.read_json(processed / 'resumen_integracion.json', typ='series'))\n"
            "pd.read_csv(processed / 'catalogo_columnas.csv')"
        ),
        nbf.v4.new_markdown_cell("## I. Correlaciones y ranking de senal"),
        nbf.v4.new_code_cell(
            "display(pd.read_csv(processed / 'correlaciones_numericas.csv', index_col=0))\n"
            "pd.read_csv(processed / 'senal_regresion.csv')"
        ),
        nbf.v4.new_markdown_cell("## J. Aptitud para modelos (clasif. y clustering)"),
        nbf.v4.new_code_cell(
            "display(pd.read_csv(processed / 'clasificacion_demanda_alta.csv'))\n"
            "display(pd.read_csv(processed / 'clasificacion_umbral_global.csv'))\n"
            "display(pd.read_csv(processed / 'silhouette_tiendas.csv'))\n"
            "display(pd.read_csv(processed / 'perfil_segmentos_tiendas.csv'))"
        ),
        nbf.v4.new_markdown_cell(
            "## Figuras y reporte\n"
            "Las 19 figuras se guardan en `figures/`; el reporte redactado queda en `reporte_eda.md`."
        ),
        nbf.v4.new_code_cell(
            "from pathlib import Path\n"
            "print(Path('reporte_eda.md').resolve())\n"
            "print(sorted(str(p) for p in Path('figures').glob('*.png')))"
        ),
    ]
    nb["metadata"] = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "pygments_lexer": "ipython3"},
    }
    settings.notebook_path.parent.mkdir(parents=True, exist_ok=True)
    settings.notebook_path.write_text(nbf.writes(nb), encoding="utf-8")
