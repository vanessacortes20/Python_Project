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
