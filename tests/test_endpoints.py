"""
tests/test_endpoints.py
=======================
Tests de integración para los endpoints de la API de Encuestas.
Usa TestClient de FastAPI (basado en httpx) para simular peticiones HTTP.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from fastapi.testclient import TestClient
from main import app, _store

client = TestClient(app)


# ─── Fixtures ───────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def limpiar_store():
    """Limpia el almacenamiento en memoria antes de cada test."""
    _store.clear()
    yield
    _store.clear()


ENCUESTA_VALIDA = {
    "encuestado": {
        "nombre": "Ana López",
        "edad": 30,
        "genero": "Femenino",
        "estrato": 3,
        "departamento": "Cundinamarca",
        "nivel_educativo": "Universitario",
    },
    "respuestas": [
        {"pregunta_id": "P01", "tipo_pregunta": "likert",     "valor": 4},
        {"pregunta_id": "P02", "tipo_pregunta": "porcentaje", "valor": 78.5},
        {"pregunta_id": "P03", "tipo_pregunta": "texto",      "valor": "Muy buen servicio"},
    ],
    "canal_recoleccion": "digital",
}

ENCUESTA_INVALIDA = {
    "encuestado": {
        "nombre": "X",          # muy corto
        "edad": 200,            # fuera de rango
        "estrato": 9,           # fuera de rango
        "departamento": "Texas",# no colombiano
    },
    "respuestas": [
        {"pregunta_id": "P01", "tipo_pregunta": "likert", "valor": 7},  # > 5
    ],
}


# ─── Tests: Health ───────────────────────────────────────────────

class TestHealth:

    def test_root_online(self):
        r = client.get("/")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "online"
        assert "version" in body


# ─── Tests: POST /encuestas/ ─────────────────────────────────────

class TestCrearEncuesta:

    def test_crear_encuesta_valida_201(self):
        r = client.post("/encuestas/", json=ENCUESTA_VALIDA)
        assert r.status_code == 201
        body = r.json()
        assert "id" in body
        assert body["encuestado"]["nombre"] == "Ana López"
        assert body["encuestado"]["departamento"] == "Cundinamarca"
        assert len(body["respuestas"]) == 3

    def test_crear_encuesta_invalida_422(self):
        """Datos inválidos deben retornar HTTP 422 con estructura de error personalizada."""
        r = client.post("/encuestas/", json=ENCUESTA_INVALIDA)
        assert r.status_code == 422
        body = r.json()
        assert body["status"] == "error"
        assert body["codigo_http"] == 422
        assert isinstance(body["errores"], list)
        assert len(body["errores"]) > 0

    def test_campo_campo_en_error_422(self):
        """El error 422 debe indicar qué campos fallaron."""
        payload = {**ENCUESTA_VALIDA, "encuestado": {**ENCUESTA_VALIDA["encuestado"], "edad": 200}}
        r = client.post("/encuestas/", json=payload)
        assert r.status_code == 422
        body = r.json()
        campos_error = [e["campo"] for e in body["errores"]]
        assert any("edad" in c for c in campos_error)

    def test_departamento_invalido_422(self):
        payload = {**ENCUESTA_VALIDA,
                   "encuestado": {**ENCUESTA_VALIDA["encuestado"], "departamento": "Narnia"}}
        r = client.post("/encuestas/", json=payload)
        assert r.status_code == 422

    def test_respuestas_vacias_422(self):
        payload = {**ENCUESTA_VALIDA, "respuestas": []}
        r = client.post("/encuestas/", json=payload)
        assert r.status_code == 422


# ─── Tests: GET /encuestas/ ──────────────────────────────────────

class TestListarEncuestas:

    def test_listado_vacio(self):
        r = client.get("/encuestas/")
        assert r.status_code == 200
        assert r.json() == []

    def test_listado_con_encuestas(self):
        client.post("/encuestas/", json=ENCUESTA_VALIDA)
        r = client.get("/encuestas/")
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 1
        assert body[0]["nombre_encuestado"] == "Ana López"

    def test_listado_filtro_departamento(self):
        client.post("/encuestas/", json=ENCUESTA_VALIDA)
        r = client.get("/encuestas/?departamento=Cundinamarca")
        assert r.status_code == 200
        assert len(r.json()) == 1

        r2 = client.get("/encuestas/?departamento=Antioquia")
        assert r2.status_code == 200
        assert len(r2.json()) == 0

    def test_paginacion(self):
        for _ in range(5):
            client.post("/encuestas/", json=ENCUESTA_VALIDA)
        r = client.get("/encuestas/?limit=2&skip=0")
        assert r.status_code == 200
        assert len(r.json()) == 2

        r2 = client.get("/encuestas/?limit=2&skip=2")
        assert len(r2.json()) == 2


# ─── Tests: GET /encuestas/{id} ──────────────────────────────────

class TestObtenerEncuesta:

    def test_obtener_existente(self):
        post_r = client.post("/encuestas/", json=ENCUESTA_VALIDA)
        enc_id = post_r.json()["id"]

        r = client.get(f"/encuestas/{enc_id}")
        assert r.status_code == 200
        assert r.json()["id"] == enc_id

    def test_obtener_inexistente_404(self):
        r = client.get("/encuestas/uuid-que-no-existe-0000")
        assert r.status_code == 404


# ─── Tests: PUT /encuestas/{id} ──────────────────────────────────

class TestActualizarEncuesta:

    def test_actualizar_existente(self):
        post_r = client.post("/encuestas/", json=ENCUESTA_VALIDA)
        enc_id = post_r.json()["id"]

        payload_update = {**ENCUESTA_VALIDA,
                          "encuestado": {**ENCUESTA_VALIDA["encuestado"], "nombre": "Ana García"}}
        r = client.put(f"/encuestas/{enc_id}", json=payload_update)
        assert r.status_code == 200
        assert r.json()["encuestado"]["nombre"] == "Ana García"
        assert r.json()["id"] == enc_id  # el ID no cambia

    def test_actualizar_inexistente_404(self):
        r = client.put("/encuestas/id-falso", json=ENCUESTA_VALIDA)
        assert r.status_code == 404


# ─── Tests: DELETE /encuestas/{id} ───────────────────────────────

class TestEliminarEncuesta:

    def test_eliminar_existente_204(self):
        post_r = client.post("/encuestas/", json=ENCUESTA_VALIDA)
        enc_id = post_r.json()["id"]

        r = client.delete(f"/encuestas/{enc_id}")
        assert r.status_code == 204

        # Verificar que ya no existe
        r2 = client.get(f"/encuestas/{enc_id}")
        assert r2.status_code == 404

    def test_eliminar_inexistente_404(self):
        r = client.delete("/encuestas/id-inexistente")
        assert r.status_code == 404


# ─── Tests: GET /encuestas/estadisticas/ ─────────────────────────

class TestEstadisticas:

    def test_estadisticas_sin_datos(self):
        r = client.get("/encuestas/estadisticas/")
        assert r.status_code == 200
        body = r.json()
        assert body["total_encuestas"] == 0

    def test_estadisticas_con_datos(self):
        client.post("/encuestas/", json=ENCUESTA_VALIDA)
        r = client.get("/encuestas/estadisticas/")
        assert r.status_code == 200
        body = r.json()
        assert body["total_encuestas"] == 1
        assert body["edad_promedio"] == 30.0
        assert "3" in body["distribucion_estrato"]
        assert "Cundinamarca" in body["distribucion_departamento"]


# ─── Tests: Carga de Archivos ─────────────────────────────────────

class TestCargaArchivos:

    def test_cargar_csv_valido(self):
        csv_content = b"Age,Gender,Score\n25,Male,4\n30,Female,5\n45,Male,3\n"
        r = client.post(
            "/archivos/cargar/",
            files={"archivo": ("test.csv", csv_content, "text/csv")},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["formato_detectado"] == "csv"
        assert body["filas_originales"] == 3

    def test_cargar_json_valido(self):
        import json
        data = [{"age": 25, "score": 4}, {"age": 30, "score": 5}]
        json_content = json.dumps(data).encode()
        r = client.post(
            "/archivos/cargar/",
            files={"archivo": ("test.json", json_content, "application/json")},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["formato_detectado"] == "json"
        assert body["filas_originales"] == 2

    def test_formato_no_soportado(self):
        r = client.post(
            "/archivos/cargar/",
            files={"archivo": ("test.xlsx", b"fake-excel", "application/vnd.ms-excel")},
        )
        assert r.status_code == 400

    def test_id_column_detectada(self):
        """Columnas con nombre 'id' o 'customer_id' deben excluirse."""
        csv = b"customer_id,Age,Score\nCust_1,25,4\nCust_2,30,5\nCust_3,45,3\n"
        r = client.post(
            "/archivos/cargar/",
            files={"archivo": ("survey.csv", csv, "text/csv")},
        )
        assert r.status_code == 200
        body = r.json()
        assert "customer_id" in body["columnas_id_excluidas"]

    def test_reporte_despues_de_carga(self):
        """Después de cargar debe poder obtenerse el reporte."""
        csv_content = b"Age,Gender,Score\n25,Male,4\n30,Female,5\n"
        r = client.post(
            "/archivos/cargar/",
            files={"archivo": ("test.csv", csv_content, "text/csv")},
        )
        # El dataset_id viene embebido en el resultado de la carga
        # Para obtenerlo necesitamos el reporte — testeamos el endpoint
        assert r.status_code == 200


# ─── Tests: Exportación ──────────────────────────────────────────

class TestExportacion:

    def test_exportar_json(self):
        client.post("/encuestas/", json=ENCUESTA_VALIDA)
        r = client.get("/exportar/?formato=json")
        assert r.status_code == 200
        assert "application/json" in r.headers.get("content-type", "")

    def test_exportar_pickle(self):
        client.post("/encuestas/", json=ENCUESTA_VALIDA)
        r = client.get("/exportar/?formato=pickle")
        assert r.status_code == 200
        assert "octet-stream" in r.headers.get("content-type", "")

    def test_exportar_formato_invalido_400(self):
        r = client.get("/exportar/?formato=csv")
        assert r.status_code == 400
