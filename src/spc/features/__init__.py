"""Feature engineering del motor de ML.

El motor vivo usa el feature engineering **agnóstico al esquema** de
`spc.features.generico` (parametrizado por el esquema que declara el cliente). El
feature engineering retail clavado al esquema Favorita (`temporales`, `perfiles`) se
archivó en `legacy/features/`.
"""

from __future__ import annotations

__all__: list[str] = []
