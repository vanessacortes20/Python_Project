"""
main.py
=======
Punto de entrada de la API REST — Gestión de Encuestas Poblacionales.

Tecnologías:
- FastAPI (ASGI): framework web asíncrono de alto rendimiento
- Pydantic v2: validación de datos tipada
- Uvicorn: servidor ASGI

Arquitectura de endpoints:
  POST   /encuestas/                → crear encuesta
  GET    /encuestas/                → listar todas
  GET    /encuestas/{id}            → obtener una
  PUT    /encuestas/{id}            → actualizar
  DELETE /encuestas/{id}            → eliminar
  GET    /encuestas/estadisticas/   → estadísticas globales
  POST   /archivos/cargar/          → cargar CSV/JSON/GeoJSON
  GET    /archivos/{id}/reporte/    → reporte de análisis
  GET    /exportar/                 → exportar JSON vs Pickle

NOTA ASYNC:
  - `def` (síncrono): FastAPI ejecuta la función en un thread pool.
    Apropiado para operaciones CPU-bound o librerías síncronas (pandas, sklearn).
  - `async def` (asíncrono): FastAPI ejecuta en el event loop de asyncio.
    INDISPENSABLE cuando hay I/O no bloqueante: consultas a DB async,
    llamadas HTTP externas (httpx/aiohttp), lectura de archivos async.
  - ASGI (Async Server Gateway Interface) es el estándar que habilita esta
    capacidad. A diferencia de WSGI (Flask/Django clásico), ASGI maneja
    miles de conexiones concurrentes sin crear un thread por conexión.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import (
    FastAPI,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response as FastAPIResponse
from pydantic import ValidationError

# Importaciones locales
from models import (
    BitacoraAuditoria,
    NivelEducativo,
    TipoPregunta,
    bitacora_global,
    CargaArchivoResult,
    EncuestaCompleta,
    EncuestaDB,
    EncuestaResumen,
    ErrorDetalle,
    ErrorResponse,
    EstadisticasGlobales,
    ExportacionInfo,
    ReporteAnalisis,
)
from services import (
    calcular_estadisticas,
    exportar_json,
    exportar_pickle,
    exportar_csv,
    exportar_dataset_csv,
    procesar_archivo_encuesta,
)
from validators import log_request, timer

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Configuración de logging — consola + archivo logs/encuestas.log
# Patrón BitacoraAuditoria de la actividad (bloque 16)
# ---------------------------------------------------------------------------
import os as _os

_LOGS_DIR = _os.path.join(_os.path.dirname(__file__), "logs")
_os.makedirs(_LOGS_DIR, exist_ok=True)
_LOG_FILE = _os.path.join(_LOGS_DIR, "encuestas.log")

# Formato compartido: fecha | nivel | módulo | mensaje
_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_LOG_DATE   = "%Y-%m-%d %H:%M:%S"

# Handler 1: consola (stdout — visible en uvicorn)
_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setLevel(logging.INFO)
_console_handler.setFormatter(logging.Formatter(_LOG_FORMAT, _LOG_DATE))

# Handler 2: archivo rotativo en logs/encuestas.log
from logging.handlers import RotatingFileHandler as _RotFH
_file_handler = _RotFH(
    _LOG_FILE,
    maxBytes=5 * 1024 * 1024,   # 5 MB por archivo
    backupCount=3,               # conserva encuestas.log, .1, .2, .3
    encoding="utf-8",
)
_file_handler.setLevel(logging.INFO)
_file_handler.setFormatter(logging.Formatter(_LOG_FORMAT, _LOG_DATE))

# Raíz del logger de la app: escribe en ambos destinos
logging.basicConfig(level=logging.INFO, handlers=[_console_handler, _file_handler])
logger = logging.getLogger("encuesta_api")
logger.info("=== API iniciada — logs en: %s ===", _LOG_FILE)

# ---------------------------------------------------------------------------
# Instancia FastAPI
# ---------------------------------------------------------------------------

app = FastAPI(
    title="🗳️ API de Gestión de Encuestas Poblacionales",
    description="""
## Sistema de Recolección y Validación de Datos de Encuestas

### Funcionalidades principales
- **CRUD completo** de encuestas con validación Pydantic estricta
- **Carga multi-formato**: CSV, JSON, GeoJSON (.shp via GeoJSON)
- **Limpieza automática**: detección de IDs, imputación KNN/MICE/Media/Mediana
- **Análisis estadístico**: estadísticas por columna, distribuciones, patrones de nulos
- **Exportación**: JSON (interoperable) vs Pickle (binario Python)
- **Estadísticas globales**: demográficas y por pregunta

### Modelos Pydantic
La API usa 3 modelos anidados principales:
1. `Encuestado` — datos demográficos validados
2. `RespuestaEncuesta` — respuestas individuales (Likert, porcentaje, texto)
3. `EncuestaCompleta` — contenedor con validación de integridad

### Validación
Todos los campos pasan por `@field_validator` con `mode='before'` y `mode='after'`.
Los errores devuelven HTTP 422 con estructura JSON detallada.
    """,
    version="1.0.0",
    contact={
        "name": "API Encuestas — USTA",
        "email": "encuestas@api.usta.edu.co",
    },
    license_info={"name": "MIT"},
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS (para que el frontend pueda consumir la API)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Almacenamiento en memoria (reemplazaría una DB en producción)
# ---------------------------------------------------------------------------

_store: Dict[str, EncuestaDB] = {}
_archivos_store: Dict[str, Dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Manejador personalizado de errores de validación (RF4)
# ---------------------------------------------------------------------------

from fastapi.exceptions import RequestValidationError

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Manejador personalizado de errores HTTP 422.
    Captura RequestValidationError de FastAPI y retorna JSON estructurado
    con detalle de cada campo inválido. Registra en consola cada intento fallido.
    """
    errores: List[ErrorDetalle] = []
    for error in exc.errors():
        campo = " → ".join(str(loc) for loc in error.get("loc", []))
        errores.append(
            ErrorDetalle(
                campo=campo,
                mensaje=error.get("msg", "Error de validación"),
                valor_recibido=error.get("input"),
                tipo_error=error.get("type", "unknown"),
            )
        )

    # Log del intento de ingesta inválido (consola + archivo logs/encuestas.log)
    logger.warning(
        "[VALIDATION_ERROR] %s %s — %d campo(s) inválido(s): %s",
        request.method,
        request.url.path,
        len(errores),
        [e.campo for e in errores],
    )
    # Registrar exclusión en BitacoraAuditoria — patrón PRE 16
    try:
        payload_body = await request.json()
    except Exception:
        payload_body = {}
    bitacora_global.registrar_exclusion(
        payload_original=payload_body,
        errores=[{"loc": e.campo, "msg": e.mensaje, "type": e.tipo_error} for e in errores],
        timestamp=datetime.utcnow().isoformat(),
    )

    response = ErrorResponse(
        codigo_http=422,
        mensaje_general=f"Se encontraron {len(errores)} error(es) de validación. "
                        "Revise los campos indicados.",
        errores=errores,
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=response.model_dump(mode="json"),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Manejador unificado para excepciones HTTP."""
    logger.warning("[HTTP_ERROR] %s %s → %d %s", request.method, request.url.path, exc.status_code, exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "codigo_http": exc.status_code, "mensaje": exc.detail},
    )


# ---------------------------------------------------------------------------
# Endpoints — Health
# ---------------------------------------------------------------------------

@app.get("/", tags=["Sistema"], summary="Health check", description="Verifica que la API esté en línea.")
async def root():
    """Endpoint raíz de verificación de estado."""
    return {
        "status": "online",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
        "encuestas_en_memoria": len(_store),
        "archivos_procesados": len(_archivos_store),
    }


# ---------------------------------------------------------------------------
# Endpoints — CRUD de Encuestas (RF3)
# ---------------------------------------------------------------------------

@log_request
@app.post(
    "/encuestas/",
    response_model=EncuestaDB,
    status_code=status.HTTP_201_CREATED,
    tags=["Encuestas"],
    summary="Registrar encuesta",
    description="""
Registra una encuesta completa (encuestado + respuestas) con validación exhaustiva.

**Validaciones aplicadas:**
- Edad: rango biológico [0, 120]
- Estrato: entero [1, 6] — escala colombiana
- Departamento: lista oficial de 33 departamentos/distritos colombianos
- Respuestas: coherencia tipo/valor (Likert=1-5, Porcentaje=0-100)
- Integridad: sin pregunta_id duplicados

Errores de validación devuelven **HTTP 422** con detalle de cada campo.
    """,
)
async def crear_encuesta(encuesta: EncuestaCompleta):
    """
    Crea y almacena una nueva encuesta.

    ASGI/Async: Esta función es `async def` porque en producción podría
    esperar escritura en una base de datos asíncrona (asyncpg, motor, etc.)
    sin bloquear el event loop.
    """
    nueva = EncuestaDB(**encuesta.model_dump())
    _store[nueva.id] = nueva
    # Registrar en BitacoraAuditoria (patrón PRE 16)
    bitacora_global.registrar_exito(nueva.id)
    logger.info(
        "[ENCUESTA CREADA] id=%s | encuestado=%s | estrato=%s | depto=%s | respuestas=%d",
        nueva.id, nueva.encuestado.nombre, nueva.encuestado.estrato,
        nueva.encuestado.departamento, len(nueva.respuestas)
    )
    return nueva


@timer
@app.get(
    "/encuestas/",
    response_model=List[EncuestaResumen],
    status_code=status.HTTP_200_OK,
    tags=["Encuestas"],
    summary="Listar encuestas",
    description="Retorna un listado paginado de todas las encuestas registradas.",
)
async def listar_encuestas(
    skip: int = Query(0, ge=0, description="Número de registros a omitir (paginación)"),
    limit: int = Query(100, ge=1, le=1000, description="Máximo de registros a retornar"),
    departamento: Optional[str] = Query(None, description="Filtrar por departamento"),
    estrato: Optional[int] = Query(None, ge=1, le=6, description="Filtrar por estrato"),
):
    """Lista todas las encuestas con filtros opcionales."""
    encuestas = list(_store.values())

    if departamento:
        encuestas = [e for e in encuestas if e.encuestado.departamento.lower() == departamento.lower()]
    if estrato is not None:
        encuestas = [e for e in encuestas if e.encuestado.estrato == estrato]

    encuestas_paginadas = encuestas[skip: skip + limit]
    return [
        EncuestaResumen(
            id=e.id,
            nombre_encuestado=e.encuestado.nombre,
            edad=e.encuestado.edad,
            departamento=e.encuestado.departamento,
            n_respuestas=len(e.respuestas),
            fecha_ingreso=e.fecha_ingreso,
        )
        for e in encuestas_paginadas
    ]


@timer
@app.get(
    "/encuestas/bitacora/",
    tags=["Encuestas"],
    summary="Bitácora de auditoría (intentos válidos e inválidos)",
    description="""
Retorna el resumen de la BitacoraAuditoria: validaciones exitosas, exclusiones y tasa de rechazo.
Patrón directo de BitacoraAuditoria (actividad, PRE 16).
    """,
)
@timer
async def bitacora_auditoria():
    """
    Expone el estado de la bitácora de auditoría en tiempo real.
    Útil para monitorear la calidad de los datos ingresados.
    """
    return bitacora_global.resumen()


@app.get(
    "/encuestas/estadisticas/",
    response_model=EstadisticasGlobales,
    status_code=status.HTTP_200_OK,
    tags=["Encuestas"],
    summary="Estadísticas globales",
    description="""
Genera un resumen estadístico completo de todas las encuestas:
- Promedios y distribuciones demográficas
- Distribución por estrato, departamento, género y canal
- Porcentaje de nulos por pregunta
    """,
)
async def estadisticas_globales():
    """Estadísticas agregadas de todas las encuestas."""
    stats = calcular_estadisticas(list(_store.values()))
    return EstadisticasGlobales(**stats)


@log_request
@app.get(
    "/encuestas/{encuesta_id}",
    response_model=EncuestaDB,
    status_code=status.HTTP_200_OK,
    tags=["Encuestas"],
    summary="Obtener encuesta por ID",
    description="Retorna la encuesta completa con todos sus datos validados.",
)
async def obtener_encuesta(encuesta_id: str):
    """Obtiene una encuesta específica por su UUID."""
    if encuesta_id not in _store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Encuesta con id '{encuesta_id}' no encontrada.",
        )
    return _store[encuesta_id]


@log_request
@app.put(
    "/encuestas/{encuesta_id}",
    response_model=EncuestaDB,
    status_code=status.HTTP_200_OK,
    tags=["Encuestas"],
    summary="Actualizar encuesta",
    description="Reemplaza completamente los datos de una encuesta existente con re-validación.",
)
async def actualizar_encuesta(encuesta_id: str, encuesta: EncuestaCompleta):
    """Actualiza una encuesta existente (reemplaza todos los campos)."""
    if encuesta_id not in _store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Encuesta con id '{encuesta_id}' no encontrada.",
        )
    encuesta_existente = _store[encuesta_id]
    actualizada = EncuestaDB(
        **encuesta.model_dump(),
        id=encuesta_existente.id,
        fecha_ingreso=encuesta_existente.fecha_ingreso,
    )
    _store[encuesta_id] = actualizada
    logger.info("Encuesta actualizada: id=%s", encuesta_id)
    return actualizada


@log_request
@app.delete(
    "/encuestas/{encuesta_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Encuestas"],
    summary="Eliminar encuesta",
    description="Elimina permanentemente una encuesta del sistema.",
)
async def eliminar_encuesta(encuesta_id: str):
    """Elimina una encuesta por ID."""
    if encuesta_id not in _store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Encuesta con id '{encuesta_id}' no encontrada.",
        )
    del _store[encuesta_id]
    logger.info("Encuesta eliminada: id=%s", encuesta_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Endpoints — Carga de archivos multi-formato
# ---------------------------------------------------------------------------

@app.post(
    "/archivos/cargar/",
    response_model=CargaArchivoResult,
    status_code=status.HTTP_200_OK,
    tags=["Archivos"],
    summary="Cargar archivo de encuesta",
    description="""
Carga y procesa automáticamente un archivo de encuesta en los formatos:
- **CSV** (.csv)
- **JSON** (.json) — array de objetos o FeatureCollection GeoJSON
- **GeoJSON** (.geojson) — extrae `properties` de cada Feature
- **Shapefile** (.shp) — requiere geopandas instalado

**Procesamiento automático:**
1. Detección de columnas ID (excluidas de estadísticas)
2. Imputación de nulos numéricos
3. Tratamiento de nulos categóricos
4. Generación de reporte estadístico
    """,
)
async def cargar_archivo(
    archivo: UploadFile = File(..., description="Archivo CSV, JSON o GeoJSON"),
    nombre_dataset: str = Query("", description="Nombre descriptivo para identificar este dataset"),
):
    """Carga un archivo multi-formato y ejecuta el pipeline de limpieza."""
    contenido = await archivo.read()
    nombre_ds = nombre_dataset.strip() if nombre_dataset else (archivo.filename or "archivo")
    try:
        df_limpio, resultado, reporte, resumen_imp = procesar_archivo_encuesta(
            contenido,
            archivo.filename or "archivo_sin_nombre",
        )
        _archivos_store[reporte.dataset_id] = {
            "reporte": reporte,
            "resumen_imputacion": resumen_imp,
            "df_json": df_limpio.to_json(orient="records"),
            "nombre": nombre_ds,
        }
        logger.info("Archivo '%s' cargado → %d filas, ID=%s", nombre_ds, resultado.filas_validas, reporte.dataset_id)
        return resultado
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get(
    "/archivos/ultimo-id/",
    tags=["Archivos"],
    summary="ID y nombre del último dataset procesado",
)
async def ultimo_dataset_id():
    """Retorna dataset_id y nombre del último archivo cargado."""
    if not _archivos_store:
        raise HTTPException(status_code=404, detail="No hay archivos procesados.")
    ultimo_id = list(_archivos_store.keys())[-1]
    return {"dataset_id": ultimo_id, "nombre": _archivos_store[ultimo_id].get("nombre","")}


@timer
@app.get(
    "/archivos/{dataset_id}/imputacion/",
    tags=["Archivos"],
    summary="Detalle de imputación aplicada por variable",
)
async def detalle_imputacion(dataset_id: str):
    """Retorna las decisiones de imputación por columna con criterio estadístico."""
    if dataset_id not in _archivos_store:
        raise HTTPException(status_code=404, detail="Dataset no encontrado.")
    return {"dataset_id": dataset_id, "decisiones": _archivos_store[dataset_id].get("resumen_imputacion",{})}


@timer
@app.get(
    "/archivos/{dataset_id}/reporte/",
    response_model=ReporteAnalisis,
    status_code=status.HTTP_200_OK,
    tags=["Archivos"],
    summary="Reporte de análisis de archivo",
    description="Retorna el reporte estadístico completo del archivo procesado.",
)
async def obtener_reporte_archivo(dataset_id: str):
    """Obtiene el reporte de análisis de un archivo cargado."""
    if dataset_id not in _archivos_store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset '{dataset_id}' no encontrado. Cargue el archivo primero.",
        )
    return _archivos_store[dataset_id]["reporte"]


@app.get(
    "/archivos/{dataset_id}/datos/",
    status_code=status.HTTP_200_OK,
    tags=["Archivos"],
    summary="Datos limpios de un archivo",
    description="Retorna los datos ya procesados y limpios del archivo cargado.",
)
async def obtener_datos_archivo(
    dataset_id: str,
    limit: int = Query(100, ge=1, le=10000),
):
    """Retorna los datos limpios de un archivo procesado."""
    if dataset_id not in _archivos_store:
        raise HTTPException(status_code=404, detail="Dataset no encontrado.")
    import json as json_mod
    data = json_mod.loads(_archivos_store[dataset_id]["df_json"])
    return {"dataset_id": dataset_id, "total": len(data), "datos": data[:limit]}


# ---------------------------------------------------------------------------
# Endpoints — Exportación JSON vs Pickle (bonus)
# ---------------------------------------------------------------------------

@app.get(
    "/exportar/disponibles/",
    tags=["Exportación"],
    summary="Fuentes disponibles para exportar",
    description="Lista las fuentes de datos disponibles: encuestas API y datasets cargados.",
)
async def exportar_disponibles():
    """Retorna qué datos están disponibles para exportar y en qué formatos."""
    fuentes = []
    n_enc = len(_store)
    fuentes.append({
        "id": "encuestas_api",
        "nombre": "Encuestas registradas en la API",
        "tipo": "encuestas",
        "n_registros": n_enc,
        "formatos": ["json", "pickle", "csv"],
        "disponible": n_enc > 0,
        "descripcion": f"{n_enc} encuesta(s) registradas vía formulario",
    })
    for did, meta in _archivos_store.items():
        import json as _json
        try:
            df_temp = __import__('pandas').read_json(__import__('io').StringIO(meta["df_json"]))
            n_rows = len(df_temp)
        except Exception:
            n_rows = 0
        fuentes.append({
            "id": did,
            "nombre": meta.get("nombre", "Dataset sin nombre"),
            "tipo": "dataset",
            "n_registros": n_rows,
            "formatos": ["csv", "json"],
            "disponible": True,
            "descripcion": f"Dataset cargado: {meta.get('nombre','')}",
        })
    return {"fuentes": fuentes, "total": len(fuentes)}


@app.get(
    "/exportar/",
    tags=["Exportación"],
    summary="Exportar encuestas (JSON, Pickle o CSV)",
    description="""
Exporta todas las encuestas registradas en el formato solicitado.

**JSON** — Recomendado para:
- Interoperabilidad con otros sistemas y lenguajes
- Legibilidad humana y debugging
- APIs REST y transferencia via HTTP
- Almacenamiento de largo plazo

**Pickle** — Recomendado para:
- Procesamiento interno Python de alto volumen
- Caché de objetos complejos (modelos ML, DataFrames)
- Transferencia rápida entre procesos Python

⚠️ **Advertencia Pickle**: Nunca deserialice Pickle de fuentes no confiables.
El formato puede ejecutar código arbitrario durante la deserialización.
    """,
)
async def exportar_encuestas(
    formato: str = Query("json", description="Formato: 'json', 'pickle' o 'csv'"),
    fuente: str = Query("encuestas_api", description="ID de fuente: 'encuestas_api' o dataset_id"),
):
    """Exporta encuestas en JSON, Pickle o CSV, o un dataset cargado en CSV/JSON."""
    import pandas as _pd
    import io as _io

    # Exportar dataset cargado
    if fuente != "encuestas_api":
        if fuente not in _archivos_store:
            raise HTTPException(status_code=404, detail=f"Dataset '{fuente}' no encontrado.")
        meta = _archivos_store[fuente]
        df = _pd.read_json(_io.StringIO(meta["df_json"]))
        nombre = meta.get("nombre", "dataset").replace(" ", "_")
        if formato == "csv":
            contenido, _ = exportar_dataset_csv(df)
            return FastAPIResponse(
                content=contenido, media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename={nombre}.csv"})
        elif formato == "json":
            contenido = df.to_json(orient="records", force_ascii=False, indent=2).encode("utf-8")
            return FastAPIResponse(
                content=contenido, media_type="application/json",
                headers={"Content-Disposition": f"attachment; filename={nombre}.json"})
        else:
            raise HTTPException(status_code=400, detail="Datasets solo soportan 'csv' o 'json'.")

    # Exportar encuestas de la API
    encuestas = list(_store.values())
    if not encuestas:
        raise HTTPException(status_code=400, detail="No hay encuestas registradas para exportar.")

    if formato == "json":
        contenido, tamanio = exportar_json(encuestas)
        return FastAPIResponse(content=contenido, media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=encuestas.json"})
    elif formato == "pickle":
        contenido, tamanio = exportar_pickle(encuestas)
        return FastAPIResponse(content=contenido, media_type="application/octet-stream",
            headers={"Content-Disposition": "attachment; filename=encuestas.pkl"})
    elif formato == "csv":
        contenido, tamanio = exportar_csv(encuestas)
        return FastAPIResponse(content=contenido, media_type="text/csv; charset=utf-8-sig",
            headers={"Content-Disposition": "attachment; filename=encuestas.csv"})
    else:
        raise HTTPException(status_code=400,
            detail=f"Formato '{formato}' no soportado. Use 'json', 'pickle' o 'csv'.")


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
