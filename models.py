"""
models.py
=========
Modelos Pydantic para la API de Gestión de Encuestas Poblacionales.

Arquitectura de modelos anidados:
  Encuestado → RespuestaEncuesta → EncuestaCompleta → EncuestaDB

Se utilizan tipos complejos (List, Union, Optional, Dict),
anotaciones de tipo, @field_validator con mode='before' y mode='after',
y model_config con json_schema_extra para Swagger.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
)
from pydantic import ConfigDict

from validators import (
    DEPARTAMENTOS_COLOMBIA,
    GENEROS_VALIDOS,
    normalizar_departamento,
    validar_escala_likert,
    validar_porcentaje,
)

# ---------------------------------------------------------------------------
# Sub-modelo 1: Encuestado (datos demográficos)
# ---------------------------------------------------------------------------

class Encuestado(BaseModel):
    """
    Datos demográficos del participante de la encuesta.

    Campos:
    - nombre: identidad textual (no se usa en cálculos)
    - edad: rango biológico válido [0, 120]
    - genero: categoría de género del encuestado
    - estrato: escala socioeconómica colombiana [1, 6]
    - departamento: uno de los 33 departamentos/distritos de Colombia
    - nivel_educativo: grado máximo de escolaridad alcanzado
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "nombre": "María García López",
                "edad": 34,
                "genero": "Femenino",
                "estrato": 3,
                "departamento": "Cundinamarca",
                "nivel_educativo": "Universitario",
            }
        }
    )

    nombre: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Nombre completo del encuestado",
    )
    edad: int = Field(
        ...,
        ge=0,
        le=120,
        description="Edad en años. Restricción biológica: [0, 120]",
    )
    genero: Optional[str] = Field(
        default=None,
        description="Género del encuestado. Acepta None para omitir.",
    )
    estrato: int = Field(
        ...,
        ge=1,
        le=6,
        description="Estrato socioeconómico colombiano (1 al 6)",
    )
    departamento: str = Field(
        ...,
        description=f"Departamento colombiano. Válidos: {', '.join(DEPARTAMENTOS_COLOMBIA[:5])}...",
    )
    nivel_educativo: Optional[str] = Field(
        default=None,
        description="Nivel educativo más alto alcanzado",
    )

    # --- Validadores ---

    @field_validator("edad", mode="before")
    @classmethod
    def edad_debe_ser_numero(cls, v: Any) -> int:
        """
        mode='before': se ejecuta ANTES de la validación de tipo de Pydantic.
        Permite convertir strings numéricos ("34") a int antes de validar el rango.
        """
        if isinstance(v, str):
            v = v.strip()
            if not v.isdigit():
                raise ValueError(f"La edad debe ser un número entero, se recibió: '{v}'")
            v = int(v)
        if not isinstance(v, (int, float)):
            raise ValueError(f"La edad debe ser numérica, se recibió tipo: {type(v).__name__}")
        return int(v)

    @field_validator("edad", mode="after")
    @classmethod
    def edad_rango_biologico(cls, v: int) -> int:
        """
        mode='after': se ejecuta DESPUÉS de la conversión de tipo.
        Aquí se aplica la restricción de dominio estadístico: [0, 120].
        """
        if not (0 <= v <= 120):
            raise ValueError(
                f"Edad {v} fuera del rango biológico válido [0, 120]. "
                "Valores extremos deben verificarse manualmente."
            )
        return v

    @field_validator("estrato", mode="before")
    @classmethod
    def estrato_coercion(cls, v: Any) -> int:
        """Convierte strings a entero antes de validar el rango."""
        if isinstance(v, str):
            try:
                return int(v.strip())
            except ValueError:
                raise ValueError(f"El estrato debe ser entero entre 1 y 6, se recibió: '{v}'")
        return v

    @field_validator("departamento", mode="before")
    @classmethod
    def departamento_normalizar(cls, v: Any) -> str:
        """
        mode='before': normaliza capitalización y espacios antes de comparar
        con la lista oficial de departamentos colombianos.
        """
        if not isinstance(v, str):
            raise ValueError("El departamento debe ser texto.")
        return normalizar_departamento(v)

    @field_validator("genero", mode="before")
    @classmethod
    def genero_normalizar(cls, v: Any) -> Optional[str]:
        """Normaliza el género a minúsculas para comparación."""
        if v is None:
            return None
        if isinstance(v, str):
            return v.strip()
        return str(v)


# ---------------------------------------------------------------------------
# Sub-modelo 2: RespuestaEncuesta (respuesta individual a una pregunta)
# ---------------------------------------------------------------------------

class RespuestaEncuesta(BaseModel):
    """
    Respuesta de un encuestado a una pregunta específica.

    Soporta múltiples tipos de respuesta mediante Union:
    - Escala Likert (1-5): preguntas de satisfacción
    - Porcentaje (0.0-100.0): preguntas cuantitativas
    - Texto libre: comentarios abiertos
    - None: respuesta omitida (MCAR/MAR explícito)
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "pregunta_id": "P01",
                "tipo_pregunta": "likert",
                "valor": 4,
                "comentario": "Muy satisfecho con el servicio",
            }
        }
    )

    pregunta_id: str = Field(
        ...,
        description="Identificador único de la pregunta (ej: 'P01', 'Q_NPS')",
        min_length=1,
        max_length=50,
    )
    tipo_pregunta: str = Field(
        ...,
        description="Tipo: 'likert', 'porcentaje', 'texto', 'binario'",
    )
    # Union[int, float, str, None] permite manejar diferentes escalas de medición
    valor: Union[int, float, str, None] = Field(
        default=None,
        description="Valor de respuesta. None indica dato faltante explícito.",
    )
    comentario: Optional[str] = Field(
        default=None,
        description="Comentario libre adicional del encuestado",
        max_length=1000,
    )

    @field_validator("tipo_pregunta", mode="before")
    @classmethod
    def tipo_pregunta_valido(cls, v: Any) -> str:
        """
        mode='before': normaliza y valida el tipo de pregunta antes del procesamiento.
        Garantiza que el pipeline estadístico sabrá cómo tratar el valor.
        """
        if not isinstance(v, str):
            raise ValueError("El tipo de pregunta debe ser texto.")
        v_norm = v.strip().lower()
        tipos_validos = {"likert", "porcentaje", "texto", "binario"}
        if v_norm not in tipos_validos:
            raise ValueError(
                f"Tipo de pregunta '{v}' no reconocido. "
                f"Tipos válidos: {tipos_validos}"
            )
        return v_norm

    @field_validator("valor", mode="after")
    @classmethod
    def valor_coherente_con_tipo(cls, v: Any, info: Any) -> Any:
        """
        mode='after': valida que el valor sea coherente con el tipo de pregunta declarado.
        Si el valor es None, se acepta como dato faltante explícito (MCAR).
        """
        if v is None:
            return v

        tipo = info.data.get("tipo_pregunta", "")

        if tipo == "likert":
            try:
                v_int = int(v)
                return validar_escala_likert(v_int)
            except (TypeError, ValueError):
                raise ValueError(
                    f"Para tipo 'likert', el valor debe ser entero entre 1 y 5. Se recibió: {v}"
                )

        if tipo == "porcentaje":
            try:
                v_float = float(v)
                return validar_porcentaje(v_float)
            except (TypeError, ValueError):
                raise ValueError(
                    f"Para tipo 'porcentaje', el valor debe ser numérico en [0.0, 100.0]. Se recibió: {v}"
                )

        if tipo == "binario":
            if str(v).lower() not in {"si", "no", "yes", "no", "true", "false", "1", "0"}:
                raise ValueError(
                    f"Para tipo 'binario', el valor debe ser sí/no. Se recibió: {v}"
                )

        return v


# ---------------------------------------------------------------------------
# Modelo contenedor 3: EncuestaCompleta
# ---------------------------------------------------------------------------

class EncuestaCompleta(BaseModel):
    """
    Modelo contenedor principal que anida Encuestado + List[RespuestaEncuesta].

    Representa la unidad mínima de análisis estadístico:
    un encuestado con su conjunto completo de respuestas.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "encuestado": {
                    "nombre": "Carlos Martínez",
                    "edad": 45,
                    "genero": "Masculino",
                    "estrato": 4,
                    "departamento": "Antioquia",
                    "nivel_educativo": "Posgrado",
                },
                "respuestas": [
                    {"pregunta_id": "P01", "tipo_pregunta": "likert", "valor": 5},
                    {"pregunta_id": "P02", "tipo_pregunta": "likert", "valor": 4},
                    {"pregunta_id": "P03", "tipo_pregunta": "texto", "valor": "Excelente atención"},
                ],
                "canal_recoleccion": "digital",
            }
        }
    )

    encuestado: Encuestado = Field(
        ...,
        description="Datos demográficos del participante",
    )
    respuestas: List[RespuestaEncuesta] = Field(
        ...,
        min_length=1,
        description="Lista de respuestas (mínimo 1). Cada item es una pregunta respondida.",
    )
    canal_recoleccion: Optional[str] = Field(
        default=None,
        description="Canal: 'digital', 'presencial', 'telefónico', etc.",
    )
    fecha_respuesta: Optional[datetime] = Field(
        default=None,
        description="Fecha y hora en que se recopiló la encuesta (ISO 8601)",
    )

    @model_validator(mode="after")
    def validar_consistencia_respuestas(self) -> "EncuestaCompleta":
        """
        Validador de modelo completo: verifica que no haya pregunta_id duplicados
        en la lista de respuestas (integridad de la encuesta).
        """
        ids = [r.pregunta_id for r in self.respuestas]
        if len(ids) != len(set(ids)):
            duplicados = [id_ for id_ in ids if ids.count(id_) > 1]
            raise ValueError(
                f"Se encontraron pregunta_id duplicados: {set(duplicados)}. "
                "Cada pregunta debe aparecer una sola vez por encuesta."
            )
        return self


# ---------------------------------------------------------------------------
# Modelos de respuesta API (sin anidamiento de entrada)
# ---------------------------------------------------------------------------

class EncuestaDB(EncuestaCompleta):
    """
    EncuestaCompleta enriquecida con metadatos del sistema para persistencia.
    Se genera internamente; el cliente nunca envía estos campos.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="UUID único generado por el sistema")
    fecha_ingreso: datetime = Field(default_factory=datetime.utcnow, description="Timestamp UTC de ingreso al sistema")


class EncuestaResumen(BaseModel):
    """Resumen ligero de una encuesta para listados."""
    id: str
    nombre_encuestado: str
    edad: int
    departamento: str
    n_respuestas: int
    fecha_ingreso: datetime


class EstadisticasGlobales(BaseModel):
    """Estadísticas agregadas de todas las encuestas registradas."""
    total_encuestas: int
    edad_promedio: Optional[float]
    edad_mediana: Optional[float]
    edad_min: Optional[int]
    edad_max: Optional[int]
    distribucion_estrato: Dict[str, int]
    distribucion_departamento: Dict[str, int]
    distribucion_genero: Dict[str, int]
    distribucion_canal: Dict[str, int]
    promedio_respuestas_por_encuesta: float
    pct_nulos_por_pregunta: Dict[str, float]


# ---------------------------------------------------------------------------
# Modelos para carga de archivos externos (CSV, JSON, Shapefile)
# ---------------------------------------------------------------------------

class CargaArchivoResult(BaseModel):
    """Resultado de la carga y procesamiento de un archivo externo de encuestas."""
    nombre_archivo: str
    formato_detectado: str
    filas_originales: int
    filas_validas: int
    filas_rechazadas: int
    columnas_id_excluidas: List[str]
    columnas_analizadas: List[str]
    nulos_antes: int
    nulos_despues: int
    metodo_imputacion: str
    errores_muestra: List[str]


class AnalisisColomnaResult(BaseModel):
    """Análisis estadístico completo de una columna individual.
    Incluye normalidad (Shapiro-Wilk/D'Agostino), outliers (IQR+Z-score),
    histograma, QQ-plot y boxplot para variables numéricas.
    """
    nombre: str
    tipo_detectado: str
    es_columna_id: bool
    incluida_en_calculo: bool
    n_total: int
    n_nulos: int
    pct_nulos: float
    n_unicos: int
    media: Optional[float] = None
    mediana: Optional[float] = None
    desv_std: Optional[float] = None
    minimo: Optional[Any] = None
    maximo: Optional[Any] = None
    skewness: Optional[float] = None
    kurtosis: Optional[float] = None
    top_valores: Optional[List[Dict[str, Any]]] = None
    # Análisis estadístico avanzado
    normalidad: Optional[Dict[str, Any]] = None      # test, p-valor, conclusión
    outliers: Optional[Dict[str, Any]] = None         # IQR + Z-score
    histograma: Optional[Dict[str, Any]] = None       # bins, counts, labels
    qq_datos: Optional[Dict[str, Any]] = None         # teóricos vs observados
    boxplot_datos: Optional[Dict[str, Any]] = None    # Q1, mediana, Q3, outliers


class ReporteAnalisis(BaseModel):
    """Reporte completo de análisis exploratorio de datos de un archivo cargado."""
    dataset_id: str
    nombre_archivo: str
    total_filas: int
    total_columnas: int
    columnas_id_detectadas: List[str]
    columnas_para_analisis: List[str]
    columnas: List[AnalisisColomnaResult]
    patron_nulos: str
    recomendacion_imputacion: str
    correlacion: Optional[Dict[str, Any]] = None   # Matriz de correlación Pearson con p-valores


# ---------------------------------------------------------------------------
# Modelos para exportación (bonus: JSON vs Pickle)
# ---------------------------------------------------------------------------

class ExportacionInfo(BaseModel):
    """Información sobre una exportación de datos."""
    formato: str
    n_registros: int
    tamanio_bytes: int
    descripcion_formato: str


# ---------------------------------------------------------------------------
# Modelo de error estructurado
# ---------------------------------------------------------------------------

class ErrorDetalle(BaseModel):
    """Detalle de un error de validación en un campo específico."""
    campo: str
    mensaje: str
    valor_recibido: Optional[Any] = None
    tipo_error: str


class ErrorResponse(BaseModel):
    """Respuesta estructurada para errores de validación (HTTP 422)."""
    status: str = "error"
    codigo_http: int
    mensaje_general: str
    errores: List[ErrorDetalle]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
