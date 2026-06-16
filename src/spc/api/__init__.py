"""Capa API (FastAPI) del SPC — Fase 3.

Conoce **HTTP y el contrato de datos** (`docs/contrato_datos.md`); no conoce los
algoritmos ni la implementacion interna de los modelos. Valida la entrada contra
el contrato, delega en la capa de servicio (`spc.service`) y devuelve exactamente
la respuesta que define el contrato.

La frontera estable es el contrato; lo que cambie por dentro (modelos, features,
umbral, composicion del ensemble, segmentos) no debe romper esta capa.
"""
