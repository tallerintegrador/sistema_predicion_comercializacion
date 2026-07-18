# Dataset PYME híbrida — reconstrucción SMOTENC

Esta carpeta contiene el ciclo reproducible que parte de una **base cruda inferida** y
genera datasets equivalentes mediante SMOTENC. No contiene información histórica original
recuperada y no debe presentarse como tal.

## Estructura

```text
reconstruccion_smote/
├── crudo/            # Entrada canónica para notebooks y experimentos
├── reconstruido/     # Salida producida con SMOTENC
├── config/           # Semilla y parámetros elegidos por dominio
├── notebooks/        # Cuadernos de exploración, remuestreo y validación
├── evidencia/        # Auditorías estadísticas, funcionales y manifiesto
├── documentacion/    # Metodología y decisiones del proceso
└── qa_excel/         # Previsualizaciones usadas para revisar los Excel
```

Los archivos de evidencia y metodología que permanecen en la raíz son copias de
compatibilidad con las rutas usadas antes de esta organización. Las carpetas
`evidencia/` y `documentacion/` son las ubicaciones recomendadas para trabajo nuevo.

## Flujo de trabajo

1. Leer `crudo/{dominio}_crudo.csv`.
2. Derivar la etiqueta con la regla del dominio.
3. Separar por fechas en TRAIN, VALID y TEST.
4. Ajustar escalado y SMOTENC únicamente con TRAIN.
5. Recalcular las columnas dependientes y reglas de negocio.
6. Unir TRAIN reconstruido con VALID y TEST intactos.
7. Comparar el resultado con `reconstruido/{dominio}_smotenc.csv`.
8. Registrar las métricas en `evidencia/`.

## Parámetros seleccionados

| Dominio | Retención minoritaria | `k_neighbors` | Semilla |
|---|---:|---:|---:|
| Ventas | 25 % | 3 | 42 |
| Compras | 50 % | 7 | 42 |
| Almacén | 25 % | 5 | 42 |

Para regenerar y validar:

```powershell
.\venv\Scripts\python.exe scripts\reconstruir_pyme_hibrida.py
.\venv\Scripts\python.exe scripts\evaluar_reconstruccion_smote.py
.\venv\Scripts\python.exe scripts\organizar_reconstruccion_smote.py
```

