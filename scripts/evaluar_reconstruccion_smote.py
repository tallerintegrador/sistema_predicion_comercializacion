"""Genera evidencia funcional real para target vs. reconstrucción SMOTENC.

Ejecuta una consulta representativa de clasificación, regresión y clustering por
dominio. Los valores se calculan en esta corrida; no se reutiliza evidencia manual.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from spc.catalogo.motor_catalogo import ejecutar_consulta

RAIZ = Path("pyme_hibrida")
SALIDA = RAIZ / "reconstruccion_smote"
CONSULTAS = {
    "ventas": {"clasificacion": "ven-c1", "regresion": "ven-r1", "clustering": "ven-k1"},
    "compras": {"clasificacion": "com-c1", "regresion": "com-r1", "clustering": "com-k1"},
    "almacen": {"clasificacion": "alm-c1", "regresion": "alm-r1", "clustering": "alm-k2"},
}
TOLERANCIAS = {"PR_AUC": 0.03, "F1": 0.03, "Recall": 0.03, "wape": 0.05, "silhouette": 0.05}


def _leer(path: Path) -> pd.DataFrame:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return pd.DataFrame(payload["rows"])


def _fila(
    dominio: str,
    tipo: str,
    consulta: str,
    metrica: str,
    objetivo: float,
    reconstruido: float,
    modelo_objetivo: str,
    modelo_reconstruido: str,
) -> dict[str, object]:
    diferencia = abs(float(objetivo) - float(reconstruido))
    tolerancia = TOLERANCIAS[metrica]
    return {
        "dominio": dominio,
        "tipo": tipo,
        "consulta": consulta,
        "metrica": metrica,
        "valor_objetivo": round(float(objetivo), 6),
        "valor_reconstruido": round(float(reconstruido), 6),
        "diferencia_absoluta": round(diferencia, 6),
        "tolerancia": tolerancia,
        "cumple": diferencia <= tolerancia,
        "modelo_objetivo": modelo_objetivo,
        "modelo_reconstruido": modelo_reconstruido,
    }


def main() -> None:
    filas: list[dict[str, object]] = []
    detalles_remuestreo: dict[str, object] = {}
    for dominio, consultas in CONSULTAS.items():
        target = _leer(RAIZ / f"{dominio}_v3.json")
        reconstruido = _leer(SALIDA / "reconstruido" / f"{dominio}_smotenc.json")
        for tipo, consulta in consultas.items():
            original = ejecutar_consulta(consulta, target)
            replica = ejecutar_consulta(consulta, reconstruido)
            if tipo == "clasificacion":
                detalles_remuestreo[dominio] = {
                    "objetivo": original.meta.get("resampling"),
                    "reconstruido": replica.meta.get("resampling"),
                }
                for metrica in ("PR_AUC", "F1", "Recall"):
                    filas.append(
                        _fila(
                            dominio,
                            tipo,
                            consulta,
                            metrica,
                            original.meta["test_metrics"][metrica],
                            replica.meta["test_metrics"][metrica],
                            original.modelo_ganador,
                            replica.modelo_ganador,
                        )
                    )
            else:
                metrica = "wape" if tipo == "regresion" else "silhouette"
                filas.append(
                    _fila(
                        dominio,
                        tipo,
                        consulta,
                        metrica,
                        original.valor_metrica,
                        replica.valor_metrica,
                        original.modelo_ganador,
                        replica.modelo_ganador,
                    )
                )

    evidencia = pd.DataFrame(filas)
    evidencia.to_csv(SALIDA / "evidencia_metricas_modelos.csv", index=False, lineterminator="\n")

    estadistica = pd.read_csv(SALIDA / "evidencia_smote_reconstruccion.csv")
    # La selección del generador ya registra estas métricas. Se eliminan aquí para
    # reemplazarlas por la verificación independiente recién ejecutada, sin sufijos _x/_y.
    estadistica = estadistica.drop(
        columns=[
            "diferencia_pr_auc",
            "diferencia_f1",
            "diferencia_recall",
            "diferencia_wape",
            "diferencia_silhouette",
            "metricas_modelos_cumplen",
        ],
        errors="ignore",
    )
    pivote = evidencia.pivot_table(
        index="dominio", columns="metrica", values="diferencia_absoluta", aggfunc="max"
    ).reset_index()
    pivote.columns = [
        "dominio" if c == "dominio" else f"diferencia_{str(c).lower()}" for c in pivote.columns
    ]
    cumple = evidencia.groupby("dominio", as_index=False)["cumple"].all().rename(
        columns={"cumple": "metricas_modelos_cumplen"}
    )
    consolidada = estadistica.merge(pivote, on="dominio", how="left").merge(
        cumple, on="dominio", how="left"
    )
    consolidada["aceptacion_total"] = (
        consolidada["cumple"].astype(bool) & consolidada["metricas_modelos_cumplen"].astype(bool)
    )
    consolidada.to_csv(SALIDA / "evidencia_aceptacion_consolidada.csv", index=False, lineterminator="\n")
    (SALIDA / "detalle_remuestreo_backend.json").write_text(
        json.dumps(detalles_remuestreo, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    for fila in consolidada.to_dict("records"):
        print(
            f"{fila['dominio']}: aceptación_total={fila['aceptacion_total']} "
            f"métricas_modelos={fila['metricas_modelos_cumplen']}"
        )


if __name__ == "__main__":
    main()
