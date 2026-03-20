"""
validators.py
=============
Validadores auxiliares globales para la API de Gestión de Encuestas Poblacionales.
Incluye listas de referencia colombianas, detección de columnas ID y utilidades de limpieza.
"""

from __future__ import annotations

import re
import logging
import functools
import time
from typing import Any, List

logger = logging.getLogger("encuesta_api.validators")

# ---------------------------------------------------------------------------
# Constantes de dominio colombiano
# ---------------------------------------------------------------------------

DEPARTAMENTOS_COLOMBIA: List[str] = [
    "Amazonas", "Antioquia", "Arauca", "Atlántico", "Bolívar",
    "Boyacá", "Caldas", "Caquetá", "Casanare", "Cauca",
    "Cesar", "Chocó", "Córdoba", "Cundinamarca", "Guainía",
    "Guaviare", "Huila", "La Guajira", "Magdalena", "Meta",
    "Nariño", "Norte de Santander", "Putumayo", "Quindío",
    "Risaralda", "San Andrés y Providencia", "Santander",
    "Sucre", "Tolima", "Valle del Cauca", "Vaupés", "Vichada",
    "Bogotá D.C.",
]

DEPARTAMENTOS_NORMALIZADOS: List[str] = [d.lower().strip() for d in DEPARTAMENTOS_COLOMBIA]

GENEROS_VALIDOS: List[str] = [
    "masculino", "femenino", "otro", "prefiero no decir",
    "male", "female", "other", "non-binary",
]

ESCALAS_LIKERT_VALIDAS = {1, 2, 3, 4, 5}

# ---------------------------------------------------------------------------
# Detección de columnas ID
# ---------------------------------------------------------------------------

# Patrones de nombres que sugieren que una columna numérica es un identificador
# (y debe excluirse de cálculos estadísticos)
ID_COLUMN_NAME_PATTERNS: List[str] = [
    r"^id$",
    r"^.*_id$",
    r"^id_.*$",
    r"^.*id$",
    r"^codigo$",
    r"^code$",
    r"^customer_id$",
    r"^cust_.*$",
    r"^folio$",
    r"^numero$",
    r"^num$",
    r"^uuid$",
    r"^key$",
    r"^pk$",
    r"^serial$",
]

_ID_REGEXES = [re.compile(p, re.IGNORECASE) for p in ID_COLUMN_NAME_PATTERNS]


def es_columna_id(nombre_columna: str, serie: Any = None) -> bool:
    """
    Determina si una columna numérica representa un identificador de persona/registro
    y por tanto debe excluirse de los cálculos estadísticos.

    Criterios:
    1. El nombre coincide con patrones típicos de ID (id, customer_id, codigo, etc.)
    2. Si se provee la serie, verifica que todos los valores son únicos (cardinalidad = 100%)
       o que los valores parecen códigos secuenciales.

    Parameters
    ----------
    nombre_columna : str
        Nombre de la columna a evaluar.
    serie : pd.Series, optional
        La serie de datos para verificación estadística adicional.

    Returns
    -------
    bool
        True si la columna parece ser un identificador.
    """
    col_lower = nombre_columna.lower().strip()

    # Criterio 1: nombre coincide con patrones de ID
    for pattern in _ID_REGEXES:
        if pattern.match(col_lower):
            return True

    # Criterio 2: verificación estadística si se provee la serie
    if serie is not None:
        try:
            import pandas as pd
            if pd.api.types.is_numeric_dtype(serie):
                n_total = len(serie.dropna())
                n_unicos = serie.nunique()
                if n_total > 0 and n_unicos == n_total:
                    # Cardinalidad perfecta → muy probable que sea ID
                    return True
                # Verificar si son enteros secuenciales
                if pd.api.types.is_integer_dtype(serie):
                    sorted_vals = serie.dropna().sort_values().reset_index(drop=True)
                    if len(sorted_vals) > 1:
                        diffs = sorted_vals.diff().dropna()
                        if (diffs == 1).all():
                            return True
        except Exception:
            pass

    return False


# ---------------------------------------------------------------------------
# Validadores de texto
# ---------------------------------------------------------------------------

def normalizar_departamento(valor: str) -> str:
    """
    Normaliza y valida que un departamento pertenece a Colombia.
    Retorna el nombre normalizado con la capitalización oficial.
    """
    valor_norm = valor.strip().lower()
    if valor_norm in DEPARTAMENTOS_NORMALIZADOS:
        idx = DEPARTAMENTOS_NORMALIZADOS.index(valor_norm)
        return DEPARTAMENTOS_COLOMBIA[idx]
    raise ValueError(
        f"Departamento '{valor}' no es válido. "
        f"Debe ser uno de los 32 departamentos de Colombia o Bogotá D.C."
    )


def validar_escala_likert(valor: int) -> int:
    """Valida que un valor esté en escala Likert (1-5)."""
    if valor not in ESCALAS_LIKERT_VALIDAS:
        raise ValueError(f"El valor {valor} no es válido en escala Likert. Debe ser 1, 2, 3, 4 o 5.")
    return valor


def validar_porcentaje(valor: float) -> float:
    """Valida que un valor esté en rango [0.0, 100.0]."""
    if not (0.0 <= valor <= 100.0):
        raise ValueError(f"El porcentaje {valor} está fuera del rango [0.0, 100.0].")
    return valor
