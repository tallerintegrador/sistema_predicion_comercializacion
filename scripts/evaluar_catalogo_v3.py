"""Informe reproducible del catálogo v3: métrica de cada consulta vs. su baseline.

Complementa `evaluar_modelos.py` (que evalúa el motor /v2 deprecado). Aquí se corren las 30
consultas del catálogo ACTIVO (`spc.catalogo.motor_catalogo`) sobre datos sintéticos y se
imprime, por consulta, la métrica de TEST, la del baseline (cuando aplica) y la calidad/aviso.
Sirve como evidencia de honestidad anti-fuga (auditoría 2026-07-03).

Uso::

    python scripts/evaluar_catalogo_v3.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(_RAIZ / "src"))

from spc.catalogo.config import obtener_modulo  # noqa: E402
from spc.catalogo.motor_catalogo import ejecutar_consulta  # noqa: E402
from spc.synthetic import generar_dominio  # noqa: E402

_PARAMS = {
    "ventas": dict(n_tiendas=8, n_productos=40, n_dias=365),
    "compras": dict(n_proveedores=20, n_productos=20, n_ordenes_por_serie=52),
    "almacen": dict(n_tiendas=8, n_productos=40, n_dias=365),
}


def main() -> int:
    print("== Evaluación del catálogo v3 (30 consultas, semilla 42) ==\n", flush=True)
    for dominio, params in _PARAMS.items():
        df = generar_dominio(dominio, seed=42, **params)
        print(f"### {dominio.upper()} (filas={len(df)})", flush=True)
        for consulta in obtener_modulo(dominio).consultas.values():
            res = ejecutar_consulta(consulta.id, df)
            base = next(
                (f.valor for f in res.tabla_comparacion if f.modelo == "baseline"), None
            )
            base_txt = f" | baseline={base:.3f}" if base is not None else ""
            aviso = " [AVISO]" if res.advertencia else ""
            print(
                f"  {consulta.id:8s} [{res.tipo[:5]}] {res.metrica_ganador:>12s}="
                f"{res.valor_metrica:.3f}{base_txt}  ganador={res.modelo_ganador} "
                f"calidad={res.calidad}{aviso}",
                flush=True,
            )
        print("", flush=True)
    print("LISTO_EVAL_V3", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
