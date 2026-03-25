# SurveyLab — API de Gestión de Encuestas Poblacionales
### Python para APIs e IA · USTA · Diseñado por Javier Mauricio Sierra

---

## Descripción del Proyecto

API REST completa construida con **FastAPI** que simula un sistema de recolección, validación y análisis estadístico de datos de encuestas poblacionales. El dominio del problema es el dataset **Customer Feedback Survey** (Kaggle, 9 000 filas), que evalúa la experiencia de clientes de una plataforma de e-commerce en cuatro dimensiones: calidad de producto, velocidad de entrega, atención al cliente y proceso de devoluciones.

La validación actúa como *"aduana transaccional"*: impide que datos inconsistentes, fuera de rango o estructuralmente inválidos contaminen el repositorio de análisis.

---

## Estructura del Proyecto (RT3)

```
encuesta-api/
├── main.py          # FastAPI: endpoints, handlers 422, logging, decoradores
├── models.py        # Pydantic: Encuestado, RespuestaEncuesta, EncuestaCompleta,
│                    #           NivelEducativo (Enum), TipoPregunta (Enum),
│                    #           BitacoraAuditoria, Annotated, Literal, ClassVar
├── validators.py    # Validadores auxiliares: departamentos, decoradores @timer/@log_request
├── services.py      # Pipeline estadístico: AnalizadorEncuesta, ImputadorInteligente
├── client.py        # (Bonus) Cliente Python httpx consumidor de la API
├── index.html       # Frontend SPA: pipeline completo, Likert interactivo, gráficas
├── requirements.txt # Dependencias del proyecto
├── README.md        # Este archivo
├── .gitignore       # Exclusiones: __pycache__, .venv/, logs/, *.pyc
├── logs/            # Generado en ejecución: encuestas.log (RotatingFileHandler)
├── data/
│   └── customer_feedback_survey.csv  # Dataset con nulos aleatorios ≤20%
└── tests/           # (Bonus) Tests con pytest
    ├── test_models.py
    └── test_endpoints.py
```

---

## Instalación y Ejecución (RT1)

### Prerrequisitos
- Python 3.11 (recomendado — wheels precompilados para todas las dependencias)
- En Windows: instalar en `C:\py311\` o usar `py -3.11`

### 1. Crear entorno virtual

**Windows:**
```cmd
C:\py311\python.exe -m venv .venv
.venv\Scripts\activate
```

**Linux/macOS:**
```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

> **¿Por qué venv y no conda?**  
> `venv` es la solución estándar de la biblioteca estándar de Python (PEP 405), sin dependencias externas. `conda` agrega un gestor de paquetes propio que puede generar conflictos con `pip` en proyectos puramente Python. Para APIs FastAPI orientadas a producción, `venv` + `pip` es la práctica recomendada.

### 2. Instalar dependencias

```cmd
pip install -r requirements.txt
```

### 3. Ejecutar la API

```cmd
cd encuesta-api
uvicorn main:app --reload
```

La API quedará disponible en:
- **API:** http://localhost:8000
- **Swagger UI (RT4):** http://localhost:8000/docs  
- **ReDoc (RT4):** http://localhost:8000/redoc

### 4. Abrir el frontend

Abrir `index.html` directamente en el navegador (doble clic o `File > Open`).

---

## Requerimientos Funcionales

### RF1 · Modelos Pydantic con Tipos Complejos

Tres modelos anidados con tipos complejos:

| Modelo | Descripción | Tipos usados |
|--------|-------------|--------------|
| `Encuestado` | Datos demográficos del participante | `Annotated[int, Field(ge=0,le=120)]`, `NivelEducativo(str,Enum)`, `Optional[str]` |
| `RespuestaEncuesta` | Respuesta individual a una pregunta | `Union[int, float, str, None]`, `TipoPregunta(str,Enum)`, `ClassVar`, `Optional[str]` |
| `EncuestaCompleta` | Modelo contenedor jerárquico | `List[RespuestaEncuesta]`, `@model_validator(mode="after")` |
| `EncuestaDB` | Extiende EncuestaCompleta con UUID + timestamp | `uuid.UUID`, `datetime` |

Patrones de la actividad aplicados explícitamente:
- `Annotated[T, Field(...)]` — restricciones embebidas en el tipo (PRE 3, PRE 16)
- `NivelEducativo(str, Enum)` y `TipoPregunta(str, Enum)` — dominio cerrado serializable (PRE 12)
- `ClassVar[frozenset]` — constantes de clase compartidas entre instancias (PRE 5)
- `BitacoraAuditoria` — registro forense de exclusiones y validaciones (PRE 16)
- `typing_extensions` — retrocompatibilidad de `Annotated`/`Literal` en Python < 3.9

### RF2 · Validadores de Campo con `@field_validator`

| Campo | mode | Validación |
|-------|------|------------|
| `edad` | `before` | Rechaza letras, decimales, vacíos; convierte string→int |
| `edad` | `after` | Rango biológico [0, 120] |
| `estrato` | `before` | Rechaza letras, decimales, vacíos; convierte string→int |
| `estrato` | `after` | Escala DANE [1, 6] |
| `nombre` | `after` | Mínimo dos palabras (nombre + apellido) |
| `departamento` | `before` | Normaliza capitalización; valida contra 33 departamentos colombianos |
| `tipo_pregunta` | `before` | Normaliza a lowercase; valida contra `TipoPregunta` Enum |
| `valor` | `after` | Coherencia tipo/valor: Likert∈[1,5], Porcentaje∈[0,100], Binario∈{Si/No} |
| `comentario` | `after` | Límite de 60 palabras |

### RF3 · Endpoints API REST

| Verbo | Ruta | Descripción | Status |
|-------|------|-------------|--------|
| POST | `/encuestas/` | Registrar encuesta | 201 / 422 |
| GET | `/encuestas/` | Listar con filtros y paginación | 200 |
| GET | `/encuestas/{id}` | Obtener por UUID | 200 / 404 |
| PUT | `/encuestas/{id}` | Actualizar encuesta | 200 / 404 |
| DELETE | `/encuestas/{id}` | Eliminar encuesta | 204 / 404 |
| GET | `/encuestas/estadisticas/` | Resumen estadístico | 200 |
| GET | `/encuestas/bitacora/` | Bitácora de auditoría | 200 |
| POST | `/archivos/cargar/` | Upload CSV/JSON/GeoJSON | 200 / 400 |
| GET | `/archivos/{id}/reporte/` | EDA completo (normalidad, outliers, QQ) | 200 |
| GET | `/archivos/{id}/imputacion/` | Decisiones de imputación por variable | 200 |
| GET | `/exportar/disponibles/` | Fuentes disponibles | 200 |
| GET | `/exportar/` | Exportar JSON, Pickle o CSV | 200 |

### RF4 · Manejo de Errores HTTP 422

Handler personalizado `@app.exception_handler(RequestValidationError)` que:
- Captura `RequestValidationError` de FastAPI/Pydantic
- Retorna JSON estructurado con `ErrorResponse` (campo, mensaje, valor recibido, tipo de error)
- Registra en consola (`stdout`) y en `logs/encuestas.log` cada intento inválido
- Registra la exclusión en `BitacoraAuditoria` con metadatos forenses (patrón PRE 16)

```json
{
  "status": "error",
  "codigo_http": 422,
  "mensaje_general": "Se encontraron 2 error(es) de validación.",
  "errores": [
    {
      "campo": "body → encuestado → edad",
      "mensaje": "Edad 200 fuera del rango biológico [0, 120]",
      "valor_recibido": 200,
      "tipo_error": "value_error"
    }
  ]
}
```

### RF5 · Endpoint Asíncrono

Todos los endpoints usan `async def`. El archivo `main.py` incluye comentario explicativo sobre:
- Diferencia entre `def` y `async def` en FastAPI
- Escenario práctico donde `async/await` es indispensable (I/O de base de datos)
- Relación entre ASGI (Uvicorn) y la capacidad asíncrona de FastAPI

---

## Requerimientos Técnicos y de Entrega

### RT1 · Entorno Virtual
- `venv` estándar de Python (ver instrucciones arriba)
- `requirements.txt` completo y funcional

### RT2 · Control de Versiones Git
- Repositorio con mínimo 5 commits significativos
- Estrategia de branching: `main` + `develop`
- `.gitignore` configurado (excluye `__pycache__`, `.venv/`, `logs/`, `*.pyc`, `*.pkl`)

### RT3 · Estructura Modular
Ver árbol de archivos al inicio de este README.

### RT4 · Documentación Automática
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Todos los modelos tienen `model_config` con `json_schema_extra` (ejemplos JSON)
- Todos los endpoints tienen `summary` y `description`

### RT5 · Decoradores Personalizados

```python
# validators.py
@log_request     # Registra: fecha, método HTTP, ruta, tiempo de respuesta
@timer           # Mide y registra tiempo de ejecución (async-aware con functools.wraps)
```

Ambos decoradores son funciones de orden superior que preservan la firma original con `@functools.wraps`, compatibles con `async def` y `def`.

---

## Logging a Archivo (logs/encuestas.log)

El sistema utiliza `logging.handlers.RotatingFileHandler`:
- Archivo: `logs/encuestas.log` (creado automáticamente al iniciar)
- Rotación: 5 MB por archivo, conserva 3 respaldos
- Formato: `YYYY-MM-DD HH:MM:SS | LEVEL | módulo | mensaje`
- Registra: encuestas creadas, errores 422, archivos cargados, tiempos de endpoints

---

## Bonificaciones

### +0.1 Tests unitarios (pytest)
```cmd
pip install pytest httpx
pytest tests/ -v
```
13 tests en `test_models.py` + 12 tests en `test_endpoints.py`.

### +0.1 Serialización JSON vs Pickle
Endpoint `GET /exportar/?formato=json|pickle|csv&fuente=encuestas_api|{dataset_id}`.

| Aspecto | JSON | Pickle |
|---------|------|--------|
| Legibilidad | ✅ Texto plano | ❌ Binario |
| Interoperabilidad | ✅ Universal | ❌ Solo Python |
| Velocidad | ⚠️ Moderada | ✅ 3–10× más rápido |
| Seguridad | ✅ Seguro | ⚠️ Riesgo RCE |
| Uso recomendado | APIs, persistencia | Caché, ML pipelines |

### +0.1 Cliente Python consumidor
```cmd
python client.py --file data/customer_feedback_survey.csv
python client.py --demo
```

---

## Dataset: Customer Feedback Survey

- **Fuente:** Kaggle — Customer Feedback Survey Dataset  
- **Filas:** 9 000 · **Columnas:** 10  
- **Variable ID detectada automáticamente:** `Customer_ID` (excluida de cálculos)
- **Variables Likert (1–5):** `Shopping_Experience`, `Product_Quality`, `Delivery_Speed`, `Customer_Service`
- **Variables binarias:** `Return_Experience`, `Recommendation`
- **Variable texto:** `Comments`
- **Nulos introducidos:** ~7.8% distribuidos naturalmente (≤20% global, 0% en IDs)

---

*USTA · Python para APIs e IA · Docente: Javier Mauricio Sierra*
