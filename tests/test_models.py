"""
tests/test_models.py
====================
Tests unitarios para los modelos Pydantic de la API de Encuestas.
Cubre validadores @field_validator, modelos anidados y casos de error.
"""

import pytest
from pydantic import ValidationError

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from models import Encuestado, RespuestaEncuesta, EncuestaCompleta


# ─── Tests: Encuestado ───────────────────────────────────────────

class TestEncuestado:

    def test_encuestado_valido(self):
        enc = Encuestado(
            nombre="Ana Pérez",
            edad=30,
            genero="Femenino",
            estrato=3,
            departamento="Cundinamarca",
        )
        assert enc.nombre == "Ana Pérez"
        assert enc.edad == 30
        assert enc.estrato == 3
        assert enc.departamento == "Cundinamarca"

    def test_edad_como_string_se_convierte(self):
        """mode='before': string numérico debe convertirse a int."""
        enc = Encuestado(nombre="Test", edad="25", estrato=2, departamento="Antioquia")
        assert enc.edad == 25

    def test_edad_fuera_de_rango_mayor(self):
        """Edad > 120 debe fallar con ValidationError (mode='after')."""
        with pytest.raises(ValidationError) as exc_info:
            Encuestado(nombre="Test", edad=150, estrato=2, departamento="Antioquia")
        errors = exc_info.value.errors()
        assert any("120" in str(e) or "rango" in e.get("msg","").lower() for e in errors)

    def test_edad_negativa(self):
        """Edad < 0 debe fallar."""
        with pytest.raises(ValidationError):
            Encuestado(nombre="Test", edad=-1, estrato=2, departamento="Antioquia")

    def test_estrato_fuera_de_rango(self):
        """Estrato > 6 o < 1 debe fallar."""
        with pytest.raises(ValidationError):
            Encuestado(nombre="Test", edad=25, estrato=7, departamento="Antioquia")
        with pytest.raises(ValidationError):
            Encuestado(nombre="Test", edad=25, estrato=0, departamento="Antioquia")

    def test_departamento_invalido(self):
        """Departamento no colombiano debe fallar."""
        with pytest.raises(ValidationError) as exc_info:
            Encuestado(nombre="Test", edad=25, estrato=3, departamento="Texas")
        assert "Texas" in str(exc_info.value) or "válido" in str(exc_info.value)

    def test_departamento_normalizacion_case_insensitive(self):
        """'cundinamarca' en minúsculas debe normalizarse."""
        enc = Encuestado(nombre="Test", edad=25, estrato=3, departamento="cundinamarca")
        assert enc.departamento == "Cundinamarca"

    def test_departamento_bogota(self):
        """Bogotá D.C. debe ser válido."""
        enc = Encuestado(nombre="Test", edad=25, estrato=4, departamento="bogotá d.c.")
        assert enc.departamento == "Bogotá D.C."

    def test_nombre_muy_corto(self):
        """Nombre de 1 caracter debe fallar (min_length=2)."""
        with pytest.raises(ValidationError):
            Encuestado(nombre="X", edad=25, estrato=2, departamento="Antioquia")

    def test_genero_opcional_none(self):
        """Género opcional puede ser None."""
        enc = Encuestado(nombre="Test", edad=25, estrato=2, departamento="Antioquia", genero=None)
        assert enc.genero is None


# ─── Tests: RespuestaEncuesta ───────────────────────────────────

class TestRespuestaEncuesta:

    def test_likert_valido(self):
        r = RespuestaEncuesta(pregunta_id="P01", tipo_pregunta="likert", valor=4)
        assert r.valor == 4

    def test_likert_fuera_de_rango(self):
        """Valor Likert 6 debe fallar."""
        with pytest.raises(ValidationError):
            RespuestaEncuesta(pregunta_id="P01", tipo_pregunta="likert", valor=6)

    def test_porcentaje_valido(self):
        r = RespuestaEncuesta(pregunta_id="P02", tipo_pregunta="porcentaje", valor=75.5)
        assert r.valor == 75.5

    def test_porcentaje_fuera_de_rango(self):
        """Porcentaje > 100 debe fallar."""
        with pytest.raises(ValidationError):
            RespuestaEncuesta(pregunta_id="P02", tipo_pregunta="porcentaje", valor=105.0)

    def test_texto_libre(self):
        r = RespuestaEncuesta(pregunta_id="P03", tipo_pregunta="texto", valor="Excelente servicio")
        assert r.valor == "Excelente servicio"

    def test_valor_none_es_dato_faltante(self):
        """None como valor es dato faltante explícito (MCAR) — debe aceptarse."""
        r = RespuestaEncuesta(pregunta_id="P04", tipo_pregunta="likert", valor=None)
        assert r.valor is None

    def test_tipo_pregunta_invalido(self):
        """Tipo de pregunta desconocido debe fallar."""
        with pytest.raises(ValidationError):
            RespuestaEncuesta(pregunta_id="P01", tipo_pregunta="invalido", valor=3)

    def test_tipo_normalizado_a_minusculas(self):
        """Tipo 'LIKERT' debe normalizarse a 'likert'."""
        r = RespuestaEncuesta(pregunta_id="P01", tipo_pregunta="LIKERT", valor=3)
        assert r.tipo_pregunta == "likert"


# ─── Tests: EncuestaCompleta ────────────────────────────────────

class TestEncuestaCompleta:

    def _encuestado(self):
        return {
            "nombre": "Carlos Martínez",
            "edad": 40,
            "estrato": 4,
            "departamento": "Antioquia",
        }

    def test_encuesta_completa_valida(self):
        enc = EncuestaCompleta(
            encuestado=self._encuestado(),
            respuestas=[
                {"pregunta_id": "P01", "tipo_pregunta": "likert", "valor": 5},
                {"pregunta_id": "P02", "tipo_pregunta": "texto",  "valor": "Bien"},
            ],
        )
        assert len(enc.respuestas) == 2

    def test_pregunta_id_duplicados_falla(self):
        """Preguntas duplicadas deben detectarse por el @model_validator."""
        with pytest.raises(ValidationError) as exc_info:
            EncuestaCompleta(
                encuestado=self._encuestado(),
                respuestas=[
                    {"pregunta_id": "P01", "tipo_pregunta": "likert", "valor": 4},
                    {"pregunta_id": "P01", "tipo_pregunta": "likert", "valor": 3},
                ],
            )
        assert "duplicad" in str(exc_info.value).lower() or "P01" in str(exc_info.value)

    def test_respuestas_vacia_falla(self):
        """Lista vacía de respuestas debe fallar (min_length=1)."""
        with pytest.raises(ValidationError):
            EncuestaCompleta(encuestado=self._encuestado(), respuestas=[])
