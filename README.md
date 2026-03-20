# 🗳️ SurveyLab — API de Gestión de Encuestas Poblacionales

> **Proyecto evaluativo · Python para APIs e IA · USTA**  
> FastAPI · Pydantic v2 · Pandas · scikit-learn · pytest

---

## 📋 Tabla de Contenidos

1. [Descripción del Proyecto](#descripción-del-proyecto)
2. [Base de Datos: Customer Feedback Survey](#base-de-datos-customer-feedback-survey)
3. [Objetivo Analítico](#objetivo-analítico)
4. [Arquitectura del Sistema](#arquitectura-del-sistema)
5. [Requerimientos Técnicos Implementados](#requerimientos-técnicos-implementados)
6. [Estructura del Proyecto](#estructura-del-proyecto)
7. [Instalación y Ejecución](#instalación-y-ejecución)
8. [Endpoints de la API](#endpoints-de-la-api)
9. [Modelos Pydantic](#modelos-pydantic)
10. [Validaciones Implementadas](#validaciones-implementadas)
11. [Pipeline de Limpieza de Datos](#pipeline-de-limpieza-de-datos)
12. [Frontend](#frontend)
13. [Tests](#tests)
14. [Cliente Python](#cliente-python)
15. [Exportación JSON vs Pickle](#exportación-json-vs-pickle)
16. [Decisiones de Diseño](#decisiones-de-diseño)

---

## 📌 Descripción del Proyecto

**SurveyLab** es una API REST completa construida con FastAPI que simula un sistema de recolección, validación, limpieza y análisis estadístico de datos de encuestas poblacionales.

El sistema actúa como una **"aduana transaccional"**: ningún dato inconsistente, fuera de rango o estructuralmente inválido puede contaminar el repositorio de análisis. Toda la validación ocurre a nivel de modelos Pydantic antes de cualquier operación sobre los datos.

### ¿Qué hace el sistema?

| Función | Descripción |
|---------|-------------|
| 📥 **Ingesta** | Recibe encuestas via API REST con validación estricta (HTTP 422 en errores) |
| 📂 **Multi-formato** | Lee CSV, JSON, GeoJSON y Shapefiles automáticamente |
| 🔑 **Detección de IDs** | Identifica y excluye columnas identificadoras de los cálculos estadísticos |
| 🧹 **Limpieza** | Pipeline automático: KNN, MICE, media/mediana según perfil de datos |
| 📊 **Análisis** | Estadísticas descriptivas, distribuciones, patrones de nulos (MCAR/MAR/MNAR) |
| 📤 **Exportación** | Serialización JSON (interoperable) vs Pickle (binario Python) |
| 🖥️ **Frontend** | Interfaz web completa ejecutable directamente en navegador |

---

## 📊 Base de Datos: Customer Feedback Survey

**Fuente:** [Kaggle — Customer Feedback Survey](https://www.kaggle.com/datasets/smmmmmmmmmmmm/customer-feedback-survey)

### Descripción del Dataset

El dataset contiene **9,000 registros** de respuestas a una encuesta de satisfacción de clientes de un e-commerce, recopiladas a través de múltiples canales.

### Variables del Dataset

| Columna | Tipo | Descripción | Rol en el Sistema |
|---------|------|-------------|-------------------|
| `Customer_ID` | String | Identificador único del cliente (ej: `Cust_1`) | 🔑 **Detectado automáticamente como ID** → excluido de cálculos |
| `Age` | Integer | Edad del encuestado en años | Variable demográfica numérica continua |
| `Gender` | Categorical | Género del encuestado (`Male`/`Female`) | Variable categórica nominal |
| `Shopping_Experience` | Integer (1–5) | Satisfacción con la experiencia de compra | Escala Likert → validada en rango [1,5] |
| `Product_Quality` | Integer (1–5) | Calificación de calidad del producto | Escala Likert → validada en rango [1,5] |
| `Delivery_Speed` | Integer (1–5) | Satisfacción con la velocidad de entrega | Escala Likert → validada en rango [1,5] |
| `Customer_Service` | Integer (1–5) | Calificación del servicio al cliente | Escala Likert → validada en rango [1,5] |
| `Return_Experience` | Categorical (Yes/No) | Experiencia con devoluciones | Variable binaria |
| `Recommendation` | Categorical (Yes/No) | Recomendaría el servicio (NPS proxy) | Variable binaria |
| `Comments` | String | Comentarios abiertos del cliente | Texto libre |

### Estadísticas Generales

```
Registros totales : 9,000
Columnas          : 10
Periodo           : Datos sintéticos de e-commerce
Nulos             : Presentes en múltiples columnas (simulando condiciones reales)
Escala de scoring : Likert 1–5 para variables de experiencia
```

### Patrones de Datos Faltantes

El dataset presenta datos faltantes en columnas de scoring y datos demográficos. El sistema clasifica estos nulos según su mecanismo de ausencia:

- **MCAR** (Missing Completely At Random): Nulos distribuidos aleatoriamente sin correlación con otras variables
- **MAR** (Missing At Random): Nulos correlacionados con otras columnas observadas
- **MNAR** (Missing Not At Random): Nulos relacionados con el valor que habría tenido la observación

---

## 🎯 Objetivo Analítico

### ¿Por qué esta encuesta?

La Customer Feedback Survey es ideal para demostrar el pipeline completo de gestión de datos de encuesta porque:

1. **Columna identificadora real**: `Customer_ID` es un ejemplo claro de columna que parece numérica/categórica pero identifica personas y **no debe incluirse en promedios ni correlaciones**. El sistema la detecta y excluye automáticamente.

2. **Múltiples tipos de variable**: Contiene numéricas discretas (Likert), categóricas (Gender), binarias (Yes/No) y texto libre (Comments), cubriendo todos los tipos de `@field_validator` implementados.

3. **Nulos realistas**: Los nulos en columnas de experiencia simulan el comportamiento de encuestados que saltan preguntas — un patrón MAR/MCAR que el pipeline de imputación debe tratar diferenciadamente.

4. **Escalas validadas**: Las respuestas de 1–5 representan directamente la escala Likert validada en los modelos Pydantic.

### ¿Qué se hará con estos datos?

```
DATOS RAW (CSV/JSON)
       ↓
  Lectura multi-formato (CSV, JSON, GeoJSON, SHP)
       ↓
  Detección de columnas ID (Customer_ID → excluida)
       ↓
  Análisis exploratorio por columna (tipo, nulos, distribución)
       ↓
  Clasificación del patrón de nulos (MCAR/MAR/MNAR)
       ↓
  Imputación inteligente:
    • Numéricos → KNN Imputer (o MICE/Media/Mediana)
    • Categóricos → Moda (si nulos < 50%) o eliminación
       ↓
  Validación Pydantic:
    • Edad: [0, 120] biológico
    • Likert: {1, 2, 3, 4, 5}
    • Nulos explícitos: None = dato faltante aceptado (MCAR)
       ↓
  Almacenamiento validado en la API
       ↓
  Estadísticas agregadas:
    • Distribuciones demográficas
    • Promedios de satisfacción
    • % de nulos por pregunta
    • NPS proxy (Recommendation)
       ↓
  Exportación JSON / Pickle para análisis downstream
```

### Hipótesis analíticas que el sistema permite explorar

- ¿Existe correlación entre estrato socioeconómico y nivel de satisfacción?
- ¿Qué preguntas tienen mayor tasa de nulos (skip rate)?
- ¿La edad del encuestado predice la probabilidad de recomendar?
- ¿El canal de recolección afecta los scores de experiencia?

---

## 🏗️ Arquitectura del Sistema

```
encuesta-api/
├── main.py          ← FastAPI app + endpoints + error handlers
├── models.py        ← Modelos Pydantic (3 anidados + respuesta)
├── validators.py    ← Validadores auxiliares + decoradores @log_request @timer
├── services.py      ← Lógica de negocio (análisis, limpieza, exportación)
├── client.py        ← Cliente Python que consume la API (bonus)
├── index.html       ← Frontend web completo (sin dependencias externas)
├── requirements.txt ← Dependencias pinadas
├── .gitignore       ← Archivos excluidos del VCS
├── data/
│   └── customer_feedback_survey.csv  ← Dataset de ejemplo
└── tests/
    ├── test_models.py    ← 20 tests unitarios de modelos Pydantic
    └── test_endpoints.py ← Tests de integración de todos los endpoints
```

---

## ✅ Requerimientos Técnicos Implementados

### RF1 — Modelos Pydantic con Tipos Complejos ✅

Tres modelos anidados con tipos complejos:

```python
Encuestado               # datos demográficos
RespuestaEncuesta        # Union[int, float, str, None], Optional[str]
EncuestaCompleta         # Encuestado + List[RespuestaEncuesta]
EncuestaDB(EncuestaCompleta)  # + id UUID + fecha_ingreso
```

### RF2 — Validadores @field_validator ✅

| Campo | mode | Regla |
|-------|------|-------|
| `edad` | `before` | Convierte strings numéricos a int |
| `edad` | `after` | Valida rango biológico [0, 120] |
| `estrato` | `before` | Coerce string → int, valida [1,6] |
| `departamento` | `before` | Normaliza y valida vs 33 departamentos colombianos |
| `tipo_pregunta` | `before` | Normaliza minúsculas, valida enum |
| `valor` | `after` | Coherencia tipo/valor (Likert=1-5, Porcentaje=0-100) |

### RF3 — Endpoints REST ✅

| Verbo | Ruta | Status |
|-------|------|--------|
| POST | `/encuestas/` | 201 / 422 |
| GET | `/encuestas/` | 200 |
| GET | `/encuestas/{id}` | 200 / 404 |
| PUT | `/encuestas/{id}` | 200 / 404 |
| DELETE | `/encuestas/{id}` | 204 / 404 |
| GET | `/encuestas/estadisticas/` | 200 |
| POST | `/archivos/cargar/` | 200 / 400 |
| GET | `/archivos/{id}/reporte/` | 200 / 404 |
| GET | `/exportar/` | 200 / 400 |

### RF4 — Manejo de Errores HTTP 422 ✅

Handler personalizado con:
- Captura `RequestValidationError` de FastAPI
- Respuesta JSON estructurada con `ErrorResponse` (Pydantic)
- Detalle de cada campo inválido (`campo`, `mensaje`, `valor_recibido`, `tipo_error`)
- Logging en consola: `[VALIDATION_ERROR] METHOD /ruta → N campo(s) inválido(s)`

### RF5 — Endpoints Asíncronos ✅

Todos los endpoints usan `async def`. Ver comentario en `main.py`:

> **`def` vs `async def` en FastAPI:**  
> Con `def`, FastAPI ejecuta la función en un thread pool externo, bloqueando ese thread.  
> Con `async def`, la función se ejecuta en el event loop de asyncio — **indispensable** cuando hay operaciones I/O no bloqueantes: queries a bases de datos async (asyncpg, motor), llamadas HTTP externas (httpx/aiohttp), lectura de archivos async.  
> **ASGI** (Async Server Gateway Interface) es el estándar que habilita esta capacidad. A diferencia de WSGI (Flask/Django clásico), ASGI maneja miles de conexiones concurrentes sin un thread por conexión.

### RT5 — Decoradores Personalizados ✅

```python
@log_request  # Registra función, args, tiempo de respuesta y errores
@timer        # Mide y registra el tiempo de ejecución en ms
```

Ambos son funciones de orden superior (como `@app.get` de FastAPI): envuelven la función original añadiendo comportamiento transversal sin modificar la lógica de negocio.

---

## 📦 Instalación y Ejecución

### Prerequisitos

- Python 3.11+
- pip

### 1. Clonar el repositorio

```bash
git clone https://github.com/tu-usuario/encuesta-api.git
cd encuesta-api
```

### 2. Crear entorno virtual

**Opción A — venv** (nativo de Python, sin dependencias adicionales, reproducible):
```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate
```

**Opción B — conda** (recomendado si se necesita gestión de versiones de Python):
```bash
conda create -n encuesta-api python=3.11
conda activate encuesta-api
```

*Decisión: Se recomienda `venv` para este proyecto por su simplicidad y ausencia de dependencias externas.*

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

> Para soporte de Shapefiles (geopandas), instale adicionalmente:
> ```bash
> pip install geopandas
> ```

### 4. Iniciar la API

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

La API estará disponible en:
- **API:** http://localhost:8000
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

### 5. Abrir el Frontend

Abra `index.html` directamente en su navegador. No requiere servidor web.

Configure la URL de la API en el campo superior derecho (por defecto: `http://localhost:8000`).

---

## 🔌 Endpoints de la API

### CRUD de Encuestas

#### `POST /encuestas/` — Registrar encuesta

```json
{
  "encuestado": {
    "nombre": "María García",
    "edad": 34,
    "genero": "Femenino",
    "estrato": 3,
    "departamento": "Cundinamarca",
    "nivel_educativo": "Universitario"
  },
  "respuestas": [
    { "pregunta_id": "P01", "tipo_pregunta": "likert",     "valor": 4 },
    { "pregunta_id": "P02", "tipo_pregunta": "porcentaje", "valor": 78.5 },
    { "pregunta_id": "P03", "tipo_pregunta": "texto",      "valor": "Excelente atención" },
    { "pregunta_id": "P04", "tipo_pregunta": "binario",    "valor": "Si" }
  ],
  "canal_recoleccion": "digital"
}
```

**Errores comunes (HTTP 422):**

```json
{
  "status": "error",
  "codigo_http": 422,
  "mensaje_general": "Se encontraron 2 error(es) de validación.",
  "errores": [
    {
      "campo": "body → encuestado → edad",
      "mensaje": "Edad 200 fuera del rango biológico válido [0, 120]",
      "valor_recibido": 200,
      "tipo_error": "value_error"
    }
  ]
}
```

#### `GET /encuestas/estadisticas/` — Estadísticas globales

Retorna:
- Promedios y distribución de edades
- Distribución por estrato, departamento, género, canal
- % de nulos por cada pregunta

### Archivos

#### `POST /archivos/cargar/` — Cargar archivo

```bash
# Con curl
curl -X POST "http://localhost:8000/archivos/cargar/?metodo_imputacion=knn" \
     -F "archivo=@data/customer_feedback_survey.csv"
```

Formatos soportados: `.csv`, `.json`, `.geojson`, `.shp`

Métodos de imputación: `knn`, `mice`, `media`, `mediana`

---

## 📐 Modelos Pydantic

### Jerarquía de modelos

```
EncuestaDB (respuesta final con ID + timestamp)
    └── EncuestaCompleta (modelo contenedor)
            ├── Encuestado (datos demográficos)
            └── List[RespuestaEncuesta] (respuestas individuales)
```

### Tipos complejos utilizados

```python
from typing import Union, Optional, List, Dict, Any

# RespuestaEncuesta.valor acepta múltiples tipos de escala
valor: Union[int, float, str, None]  # Likert | Porcentaje | Texto | Faltante

# EncuestaCompleta contiene lista de respuestas
respuestas: List[RespuestaEncuesta]  # mínimo 1 elemento

# Campos opcionales representan datos faltantes explícitos
genero: Optional[str]           # None = preferible no decir
nivel_educativo: Optional[str]  # None = no proporcionado
fecha_respuesta: Optional[datetime]
```

---

## 🧹 Pipeline de Limpieza de Datos

### 1. Detección de Columnas ID

El sistema identifica automáticamente columnas que identifican personas y las excluye de todos los cálculos estadísticos:

**Criterios de detección:**
- Nombre coincide con patrones: `id`, `*_id`, `customer_*`, `codigo`, `folio`, `pk`, etc.
- Cardinalidad perfecta: todos los valores son únicos (100%)
- Enteros secuenciales: `1, 2, 3, 4, …`

**Por qué es importante:**
> Incluir `Customer_ID = {Cust_1, Cust_2, …}` en una media o correlación no tiene sentido estadístico y contamina los resultados. El sistema separa explícitamente los identificadores de las variables analíticas.

### 2. Tratamiento de Nulos

```
Columnas NUMÉRICAS con nulos:
  ├── < 30% nulos → KNN Imputer (usa vecinos más cercanos)
  ├── 30–50% nulos → MICE (imputación multivariada encadenada)
  └── > 50% nulos → Eliminación (too many missing)

Columnas CATEGÓRICAS con nulos:
  ├── < 50% nulos → Imputar con Moda
  └── ≥ 50% nulos → Eliminar columna

Nulos EXPLÍCITOS en respuestas (valor=None):
  └── Aceptados como MCAR — representan preguntas omitidas intencionalmente
```

### 3. Métodos de Imputación Disponibles

| Método | Cuándo usar | Fortalezas |
|--------|-------------|------------|
| **KNN** | Datos con estructura multivariada, < 30% nulos | Preserva distribución local |
| **MICE** | Datos con relaciones complejas entre variables | Estadísticamente más riguroso |
| **Media** | Nulos < 5%, sin sesgo de distribución | Simple, rápido |
| **Mediana** | Distribuciones sesgadas o con outliers | Robusto a valores extremos |

---

## 🖥️ Frontend

El archivo `index.html` es un dashboard completo que:

- **No requiere servidor web** — se abre directamente en el navegador
- **Configurable** — permite cambiar la URL de la API en tiempo real
- **Dashboard** con gráficas Chart.js: distribución por estrato, género, departamento y nulos
- **Formulario de ingesta** con validación visual y carga de ejemplos
- **Listado filtrable** de todas las encuestas con modal de detalle
- **Carga de archivos** drag & drop con visualización del resultado de limpieza
- **Reporte de análisis** columna por columna con progress bars de completitud
- **Exportación** JSON vs Pickle con tabla comparativa
- **API Reference** integrada con ejemplos de payload y esquemas Pydantic

---

## 🧪 Tests

### Ejecutar todos los tests

```bash
pytest tests/ -v
```

### Ejecutar con cobertura

```bash
pytest tests/ --cov=. --cov-report=html
```

### Tests implementados (25 total)

**`test_models.py` — Tests unitarios (13):**
- Encuestado válido e inválido (edad, estrato, departamento, nombre)
- Normalización de strings a tipos numéricos (mode='before')
- Validación de rango biológico (mode='after')
- RespuestaEncuesta con todos los tipos de pregunta
- Nulos explícitos aceptados como MCAR
- EncuestaCompleta con detección de pregunta_id duplicados

**`test_endpoints.py` — Tests de integración (12):**
- Health check
- CRUD completo con status codes correctos
- Error 422 con estructura JSON personalizada
- Paginación y filtros
- Carga de CSV y JSON
- Detección de columnas ID
- Exportación JSON y Pickle

---

## 🐍 Cliente Python

```bash
# Modo demo: genera 20 encuestas aleatorias
python client.py --demo --n 20

# Cargar CSV
python client.py --file data/customer_feedback_survey.csv --limit 100

# Apuntar a API en otro host
python client.py --demo --host http://mi-api.render.com
```

El cliente genera un **reporte estadístico** automático con pandas mostrando:
- Distribución por estrato (DataFrame con porcentajes)
- Top 10 departamentos
- % nulos por pregunta con semáforo (✅ Bajo / 🟡 Medio / ⚠️ Alto)
- Estadísticas de ingesta (exitosas, fallidas, tasa de éxito)

---

## 📤 Exportación JSON vs Pickle

```bash
# JSON — texto legible, interoperable
GET /exportar/?formato=json

# Pickle — binario Python, más rápido
GET /exportar/?formato=pickle
```

| Característica | JSON | Pickle |
|---|---|---|
| Legibilidad | ✅ Texto plano | ❌ Binario |
| Interoperabilidad | ✅ Universal | ❌ Solo Python |
| Velocidad | ⚠️ Moderada | ✅ 3–10x más rápido |
| Seguridad | ✅ Seguro | ⚠️ Riesgo RCE si fuente desconocida |
| Uso | APIs, persistencia, compartir | Caché, ML pipelines |

---

## 🎨 Decisiones de Diseño

### ¿Por qué `venv` y no `conda`?

`venv` es nativo de Python (sin instalación adicional), reproducible en cualquier entorno (CI/CD, Docker, Render) y suficiente para este proyecto. `conda` agrega valor cuando se necesita gestión de versiones de Python o dependencias no-Python (GDAL para geopandas).

### ¿Por qué almacenamiento en memoria?

El proyecto utiliza un diccionario en memoria (`_store: Dict[str, EncuestaDB]`) como repositorio. Esto simplifica el despliegue (sin base de datos externa) y es apropiado para demostración. En producción se reemplazaría por PostgreSQL (asyncpg) o MongoDB (motor).

### ¿Por qué `None` para datos faltantes en respuestas?

`Union[int, float, str, None]` con `valor=None` representa explícitamente un dato faltante (MCAR). Esto es estadísticamente correcto: forzar un 0 o string vacío implicaría que el encuestado respondió algo, sesgando los análisis. `None` preserva la semántica de "pregunta omitida intencionalmente".

### ¿Por qué `mode='before'` en validadores de edad y estrato?

Porque la entrada puede venir de CSV (siempre strings) o de formularios HTML. Con `mode='before'` el validador convierte `"34"` → `34` antes de que Pydantic evalúe el tipo, garantizando que el error semántico ("fuera de rango") tenga prioridad sobre el error de tipo ("no es int").

---

## 📚 Referencias

- [FastAPI Documentation](https://fastapi.tiangolo.com)
- [Pydantic v2 Documentation](https://docs.pydantic.dev/latest/)
- [pandas Documentation](https://pandas.pydata.org/docs/)
- [scikit-learn — KNNImputer](https://scikit-learn.org/stable/modules/generated/sklearn.impute.KNNImputer.html)
- [Little & Rubin — Statistical Analysis with Missing Data](https://www.wiley.com/en-us/Statistical+Analysis+with+Missing+Data%2C+3rd+Edition-p-9780470526798)
- [Dataset: Customer Feedback Survey (Kaggle)](https://www.kaggle.com/datasets/smmmmmmmmmmmm/customer-feedback-survey)

---

## 👥 Autores

Proyecto desarrollado para la asignatura **Python para APIs e IA** — Universidad Santo Tomás (USTA)

---

*Licencia MIT — Uso libre para fines académicos*
