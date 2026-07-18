# Reconstruccion estadistica inversa con SMOTENC

Los archivos de esta carpeta son una reconstruccion inferida a partir de `pyme_hibrida`.
No representan una base historica peruana observada ni recuperan de forma exacta una fuente
desconocida. La base `crudo/` retira una fraccion de la clase minoritaria solo de TRAIN; la
carpeta `reconstruido/` recupera el tamano y la prevalencia objetivo mediante SMOTENC.

VALID y TEST se copian sin remuestreo. La seleccion prueba retenciones 25/50/75 % y
`k_neighbors` 3/5/7; se elige la menor base que satisface tanto las tolerancias estadisticas
como las diferencias maximas de PR-AUC/F1/recall, WAPE y silueta. La evidencia esta en
`evidencia_smote_reconstruccion.csv`, `evidencia_metricas_modelos.csv` y
`evidencia_aceptacion_consolidada.csv`. Semilla global: 42.

La identidad temporal (fecha y claves de negocio) de las filas retiradas se conserva como
esqueleto estructural; las variables sintetizables se generan con SMOTENC y las columnas
derivadas se recalculan aplicando las reglas del contrato.
