"""Entrenamiento por cliente bajo demanda (Camino A completo, ADR-0013).

Capa **engine-adjacent**: orquesta el experimento medido (entrenar candidato por
cliente, comparar honestamente contra el modelo congelado y un baseline, adoptar solo si
mejora) reutilizando el motor (``spc.models.regresion``) sin tocarlo. Vive aparte del
camino de predicción: lo invoca el servicio y lo dispara un endpoint, en un trabajo
asíncrono local y desacoplado.
"""
