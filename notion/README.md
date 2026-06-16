# Reportes del Backlog — SPC (Taller Integrador I)

Documentación por Historia de Usuario (HU) del **Sistema Predictivo de Comercialización (SPC)**.
Cada archivo explica **qué se hizo**, el **código puntual** que lo implementa, los **resultados**
obtenidos y las **capturas** sugeridas para el reporte de Notion.

## Índice

### Habilitadores (EN) — `notion/EN/`

Trabajo técnico transversal que no entrega valor de usuario directo pero habilita el resto.

| EN | Título | Ámbito | Estado |
|----|--------|--------|--------|
| [EN-001](EN/EN-001.md) | Configurar repositorio y estructura del proyecto | Infraestructura / tooling | ✅ |

### Requisitos no funcionales (RN) — `notion/RN/`

Restricciones de calidad que el sistema debe cumplir (no entregan función, condicionan el "cómo").

| RN | Título | Tipo | Estado |
|----|--------|------|--------|
| [RN-001](RN/RN-001.md) | Separación estricta de capas | Arquitectura | ✅ |
| [RN-002](RN/RN-002.md) | Tiempo de respuesta de la predicción | Rendimiento | ✅ |

### Tareas técnicas (TA) — `notion/TA/`

Trabajo de implementación que sostiene las HU (frontera, datos, artefactos, capas, validación).

| TA | Título | Ámbito | Estado |
|----|--------|--------|--------|
| [TA-001](TA/TA-001.md) | Definir contratos de datos por dominio | Contrato / API | ✅ |
| [TA-002](TA/TA-002.md) | Implementar pipeline de preparación de datos | Datos / features | ✅ |
| [TA-003](TA/TA-003.md) | Serializar artefactos del motor de ML | Motor / persistencia | ✅ |
| [TA-004](TA/TA-004.md) | Implementar arquitectura en capas | Arquitectura | ✅ |
| [TA-005](TA/TA-005.md) | Validación de entradas según contrato | API / robustez | ✅ |

### Historias de Usuario (HU) — `notion/HU/`

| HU | Título | Capa | Artefacto / Endpoint | Estado |
|----|--------|------|----------------------|--------|
| [HU-001](HU/HU-001.md) | Pronóstico de ventas (regresión) | Motor ML (Fase 2a) | `regresion_v3` | ✅ |
| [HU-002](HU/HU-002.md) | Reposición de compras | Servicio / negocio (Fase 3) | lógica de negocio | ✅ |
| [HU-003](HU/HU-003.md) | Clasificación de riesgo de almacén | Motor ML (Fase 2b) | `clasificacion_v1` | ✅ |
| [HU-004](HU/HU-004.md) | Segmentación por clustering | Motor ML (Fase 2c) | `clustering_{tiendas,familias}_v1` | ✅ |
| [HU-005](HU/HU-005.md) | Endpoint de pronóstico de ventas | API (Fase 3) | `POST /sales` | ✅ |
| [HU-006](HU/HU-006.md) | Endpoint de reposición de compras | API (Fase 3) | `POST /purchases` | ✅ |
| [HU-007](HU/HU-007.md) | Endpoint de riesgo de almacén | API (Fase 3) | `POST /inventory` | ✅ |

## Arquitectura por capas (contexto común)

```
HTTP / API  ──►  Servicio (negocio)  ──►  Motor de ML (artefactos)
 conoce HTTP       conoce el contrato        carga y predice;
 y el contrato     y las reglas de negocio   NO conoce HTTP
```

- **Motor de ML** (`src/spc/models/`): regresión, clasificación y clustering. Entrena offline
  (GPU para los boosters), **predice en CPU**, serializa artefactos portables en `models/`.
- **Servicio** (`src/spc/service/`): traduce el contrato genérico al esquema del motor
  (`adaptador.py`) y aplica reglas de negocio (`ventas_service`, `compras_service`, `almacen_service`).
- **API** (`src/spc/api/`): FastAPI con validación Pydantic estricta, manejo de errores uniforme y
  Swagger. Un `POST` por campo del contrato.

Decisiones de diseño: `docs/decisiones/` (ADR 0002–0007). Contrato de datos: `docs/contrato_datos.md`.

## Convención de las capturas

En cada HU, la sección **📸 Capturas sugeridas** indica exactamente qué pantalla tomar y desde
dónde. Recomendado: ejecutar los comandos / abrir Swagger en `http://127.0.0.1:8000/docs` y
capturar las respuestas `200` reales.
</content>
</invoke>
