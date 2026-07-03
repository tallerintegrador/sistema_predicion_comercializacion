"""Catálogo de 30 consultas predefinidas — SPC ADR-0028.

Este módulo implementa el catálogo declarativo de consultas automáticas, el motor de ejecución
y la carga de configuración.

Componentes:
- ``consultas.yaml`` — fuente única de verdad: 30 consultas (10 por módulo) con objetivos,
  features, candidatos y métricas.
- ``config.py`` — parsers YAML y dataclasses de configuración.
- ``motor_catalogo.py`` — ejecutor genérico que toma una consulta y entrena/evalúa/elige.
"""

__all__ = ["cargar_catalogo", "ejecutar_consulta"]
