"""
client.py
=========
Cliente Python que consume la API de Encuestas Poblacionales.
Carga datos desde un archivo CSV/JSON, los ingesta en la API
y genera un reporte estadístico con pandas.

Uso:
    python client.py --file data/customer_feedback_survey.csv
    python client.py --file data/encuestas.json --host http://localhost:8000
    python client.py --demo   # Genera y sube 20 encuestas de ejemplo
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import pandas as pd

# ─── Logging ─────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("encuesta_client")

# ─── Configuración ───────────────────────────────────────────────
DEFAULT_HOST = "http://localhost:8000"
TIMEOUT = 10.0

DEPARTAMENTOS = [
    "Cundinamarca", "Antioquia", "Valle del Cauca", "Atlántico",
    "Santander", "Bolívar", "Nariño", "Córdoba", "Meta", "Tolima",
    "Boyacá", "Caldas", "Huila", "Magdalena", "Cauca",
]

NOMBRES = [
    "Ana Martínez", "Carlos López", "María García", "José Rodríguez",
    "Laura Torres", "Daniel Pérez", "Sofía Ramírez", "Andrés Castro",
    "Valentina Moreno", "Felipe Herrera", "Isabella Díaz", "Camilo Vargas",
]

NIVELES_EDU = ["Primaria", "Secundaria", "Técnico", "Tecnólogo", "Universitario", "Posgrado"]
GENEROS = ["Masculino", "Femenino", "Otro", None]
CANALES = ["digital", "presencial", "telefónico"]


# ─── Clase Cliente ───────────────────────────────────────────────

class EncuestaAPIClient:
    """
    Cliente HTTP para la API de Encuestas Poblacionales.
    Usa httpx para peticiones síncronas con manejo de errores.
    """

    def __init__(self, base_url: str = DEFAULT_HOST):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(base_url=self.base_url, timeout=TIMEOUT)
        self.stats = {"exitosas": 0, "fallidas": 0, "errores": []}

    def health_check(self) -> bool:
        try:
            r = self.client.get("/")
            if r.status_code == 200:
                info = r.json()
                logger.info("✅ API conectada. Versión: %s | Encuestas en memoria: %d",
                            info.get("version"), info.get("encuestas_en_memoria", 0))
                return True
        except Exception as e:
            logger.error("❌ No se pudo conectar a la API: %s", e)
        return False

    def crear_encuesta(self, payload: Dict[str, Any]) -> Optional[Dict]:
        try:
            r = self.client.post("/encuestas/", json=payload)
            if r.status_code == 201:
                self.stats["exitosas"] += 1
                return r.json()
            else:
                self.stats["fallidas"] += 1
                err = r.json()
                msgs = [f"{e['campo']}: {e['mensaje']}" for e in err.get("errores", [])]
                self.stats["errores"].append("; ".join(msgs))
                return None
        except Exception as e:
            self.stats["fallidas"] += 1
            self.stats["errores"].append(str(e))
            return None

    def listar_encuestas(self, limit: int = 1000) -> List[Dict]:
        r = self.client.get(f"/encuestas/?limit={limit}")
        r.raise_for_status()
        return r.json()

    def estadisticas(self) -> Dict:
        r = self.client.get("/encuestas/estadisticas/")
        r.raise_for_status()
        return r.json()

    def cargar_csv(self, ruta: str, metodo: str = "knn") -> Dict:
        with open(ruta, "rb") as f:
            r = self.client.post(
                f"/archivos/cargar/?metodo_imputacion={metodo}",
                files={"archivo": (Path(ruta).name, f, "text/csv")},
                timeout=60,
            )
        r.raise_for_status()
        return r.json()

    def close(self):
        self.client.close()


# ─── Funciones de procesamiento ──────────────────────────────────

def encuesta_desde_fila_csv(row: pd.Series) -> Optional[Dict[str, Any]]:
    """
    Convierte una fila del CSV de customer_feedback_survey a payload de la API.
    Maneja nulos de forma explícita: None → dato faltante (MCAR).

    Columnas esperadas:
        Customer_ID, Age, Gender, Shopping_Experience, Product_Quality,
        Delivery_Speed, Customer_Service, Return_Experience, Recommendation, Comments
    """
    # Detectar y manejar nulos en edad
    edad = row.get("Age")
    if pd.isna(edad):
        logger.debug("Fila con Age=NaN omitida (ID: %s)", row.get("Customer_ID", "?"))
        return None
    try:
        edad = int(float(edad))
    except (TypeError, ValueError):
        return None

    # Normalizar género
    genero_raw = row.get("Gender")
    genero_map = {"Male": "Masculino", "Female": "Femenino"}
    genero = genero_map.get(str(genero_raw), None) if not pd.isna(genero_raw if genero_raw is not None else float('nan')) else None

    # Departamento aleatorio (el CSV no tiene departamento colombiano)
    depto = random.choice(DEPARTAMENTOS)
    # Estrato aleatorio
    estrato = random.randint(1, 6)

    # Construir respuestas a partir de columnas Likert
    respuestas = []
    mapa_preguntas = {
        "Shopping_Experience": "P01",
        "Product_Quality":     "P02",
        "Delivery_Speed":      "P03",
        "Customer_Service":    "P04",
    }
    for col, pid in mapa_preguntas.items():
        val_raw = row.get(col)
        # Nulo explícito: valor None en la API (MCAR)
        val = None if pd.isna(val_raw) else int(float(val_raw))
        respuestas.append({
            "pregunta_id": pid,
            "tipo_pregunta": "likert",
            "valor": val,
        })

    # Return_Experience como binario
    ret_raw = row.get("Return_Experience")
    if not pd.isna(ret_raw if ret_raw is not None else float('nan')):
        respuestas.append({
            "pregunta_id": "P05",
            "tipo_pregunta": "binario",
            "valor": str(ret_raw),
        })

    # Recommendation como binario
    rec_raw = row.get("Recommendation")
    if not pd.isna(rec_raw if rec_raw is not None else float('nan')):
        respuestas.append({
            "pregunta_id": "P06",
            "tipo_pregunta": "binario",
            "valor": str(rec_raw),
        })

    # Comments como texto libre
    comments = row.get("Comments")
    if not pd.isna(comments if comments is not None else float('nan')):
        respuestas.append({
            "pregunta_id": "P07",
            "tipo_pregunta": "texto",
            "valor": str(comments),
        })

    return {
        "encuestado": {
            "nombre": f"Encuestado_{row.get('Customer_ID', 'X')}",
            "edad": edad,
            "genero": genero,
            "estrato": estrato,
            "departamento": depto,
        },
        "respuestas": respuestas,
        "canal_recoleccion": "digital",
    }


def encuesta_aleatoria() -> Dict[str, Any]:
    """Genera una encuesta aleatoria para demostración."""
    return {
        "encuestado": {
            "nombre": random.choice(NOMBRES),
            "edad": random.randint(18, 75),
            "genero": random.choice(GENEROS),
            "estrato": random.randint(1, 6),
            "departamento": random.choice(DEPARTAMENTOS),
            "nivel_educativo": random.choice(NIVELES_EDU),
        },
        "respuestas": [
            {"pregunta_id": "P01", "tipo_pregunta": "likert",
             "valor": random.choice([1, 2, 3, 4, 5, None])},
            {"pregunta_id": "P02", "tipo_pregunta": "likert",
             "valor": random.randint(1, 5)},
            {"pregunta_id": "P03", "tipo_pregunta": "porcentaje",
             "valor": round(random.uniform(10, 100), 1)},
            {"pregunta_id": "P04", "tipo_pregunta": "binario",
             "valor": random.choice(["Si", "No"])},
            {"pregunta_id": "P05", "tipo_pregunta": "texto",
             "valor": random.choice(["Excelente", "Bueno", "Regular", None])},
        ],
        "canal_recoleccion": random.choice(CANALES),
    }


# ─── Reporte Estadístico ─────────────────────────────────────────

def generar_reporte(client: EncuestaAPIClient) -> None:
    """Genera y muestra un reporte estadístico completo usando pandas."""
    print("\n" + "═" * 70)
    print("📊 REPORTE ESTADÍSTICO DE ENCUESTAS")
    print("═" * 70)

    stats = client.estadisticas()
    if stats["total_encuestas"] == 0:
        print("⚠️  No hay encuestas registradas.\n")
        return

    # ── Resumen general
    print(f"\n{'RESUMEN GENERAL':─^50}")
    print(f"  Total encuestas     : {stats['total_encuestas']:,}")
    print(f"  Edad promedio       : {stats.get('edad_promedio', 'N/A')} años")
    print(f"  Edad mediana        : {stats.get('edad_mediana', 'N/A')} años")
    print(f"  Edad min/max        : {stats.get('edad_min')} / {stats.get('edad_max')}")
    print(f"  Resp. por encuesta  : {stats.get('promedio_respuestas_por_encuesta')}")

    # ── DataFrame de distribución de estrato
    print(f"\n{'DISTRIBUCIÓN POR ESTRATO':─^50}")
    df_estrato = pd.DataFrame(
        list(stats["distribucion_estrato"].items()),
        columns=["Estrato", "Frecuencia"]
    ).sort_values("Estrato")
    df_estrato["Porcentaje"] = (df_estrato["Frecuencia"] / stats["total_encuestas"] * 100).round(1)
    print(df_estrato.to_string(index=False))

    # ── DataFrame de distribución por departamento
    print(f"\n{'TOP 10 DEPARTAMENTOS':─^50}")
    df_deptos = pd.DataFrame(
        list(stats["distribucion_departamento"].items()),
        columns=["Departamento", "Frecuencia"]
    ).sort_values("Frecuencia", ascending=False).head(10)
    df_deptos["Pct"] = (df_deptos["Frecuencia"] / stats["total_encuestas"] * 100).round(1)
    print(df_deptos.to_string(index=False))

    # ── Nulos por pregunta
    if stats["pct_nulos_por_pregunta"]:
        print(f"\n{'NULOS POR PREGUNTA':─^50}")
        df_nulos = pd.DataFrame(
            list(stats["pct_nulos_por_pregunta"].items()),
            columns=["Pregunta", "% Nulos"]
        ).sort_values("% Nulos", ascending=False)
        df_nulos["Estado"] = df_nulos["% Nulos"].apply(
            lambda x: "⚠️ Alto" if x > 20 else ("🟡 Medio" if x > 5 else "✅ Bajo")
        )
        print(df_nulos.to_string(index=False))

    # ── Estadísticas del cliente
    print(f"\n{'ESTADÍSTICAS DE INGESTA':─^50}")
    total = client.stats["exitosas"] + client.stats["fallidas"]
    tasa  = (client.stats["exitosas"] / max(total, 1) * 100)
    print(f"  Encuestas enviadas  : {total}")
    print(f"  Exitosas            : {client.stats['exitosas']} ({tasa:.1f}%)")
    print(f"  Fallidas            : {client.stats['fallidas']}")
    if client.stats["errores"]:
        print(f"  Primeros errores    : {client.stats['errores'][:3]}")

    print("\n" + "═" * 70 + "\n")


# ─── Punto de entrada ────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Cliente Python para la API de Encuestas Poblacionales"
    )
    parser.add_argument("--host",  default=DEFAULT_HOST, help="URL base de la API")
    parser.add_argument("--file",  default=None,          help="Ruta al CSV o JSON a cargar")
    parser.add_argument("--demo",  action="store_true",   help="Generar encuestas de ejemplo")
    parser.add_argument("--n",     type=int, default=20,  help="Número de encuestas demo")
    parser.add_argument("--limit", type=int, default=100, help="Máx filas del CSV a procesar")
    args = parser.parse_args()

    client = EncuestaAPIClient(base_url=args.host)

    # Verificar conexión
    if not client.health_check():
        print("\n❌ No se pudo conectar a la API. Asegúrese de que esté corriendo con:")
        print("   uvicorn main:app --reload\n")
        sys.exit(1)

    # ── Modo demo
    if args.demo:
        logger.info("🎲 Generando %d encuestas de demostración…", args.n)
        t0 = time.time()
        for i in range(args.n):
            payload = encuesta_aleatoria()
            result  = client.crear_encuesta(payload)
            if result:
                logger.debug("  ✓ Encuesta %d creada: %s", i+1, result["id"][:8])
        elapsed = time.time() - t0
        logger.info("⏱️  %d encuestas procesadas en %.2f seg", args.n, elapsed)

    # ── Modo archivo
    elif args.file:
        ruta = Path(args.file)
        if not ruta.exists():
            print(f"❌ Archivo no encontrado: {ruta}")
            sys.exit(1)

        logger.info("📂 Cargando archivo: %s", ruta)

        if ruta.suffix.lower() == ".csv":
            df = pd.read_csv(ruta)
            logger.info("📊 CSV cargado: %d filas, %d columnas", len(df), len(df.columns))
            logger.info("   Columnas: %s", list(df.columns))

            # Mostrar estadísticas del CSV antes de ingestar
            print(f"\n{'ESTADÍSTICAS DEL CSV (antes de ingesta)':─^60}")
            print(f"  Filas      : {len(df):,}")
            print(f"  Columnas   : {len(df.columns)}")
            print(f"  Nulos tot. : {df.isna().sum().sum():,}")
            print(df.describe(include="all").to_string())

            # Ingestar fila por fila
            limit = min(args.limit, len(df))
            logger.info("⬆️  Ingresando hasta %d encuestas a la API…", limit)

            t0 = time.time()
            for idx, (_, row) in enumerate(df.head(limit).iterrows()):
                payload = encuesta_desde_fila_csv(row)
                if payload:
                    client.crear_encuesta(payload)
                if (idx + 1) % 25 == 0:
                    logger.info("   %d/%d procesadas…", idx+1, limit)

            elapsed = time.time() - t0
            logger.info("⏱️  %d filas procesadas en %.2f seg", limit, elapsed)

        elif ruta.suffix.lower() == ".json":
            with open(ruta) as f:
                data = json.load(f)
            if not isinstance(data, list):
                data = [data]
            logger.info("📋 JSON cargado: %d registros", len(data))
            for item in data[:args.limit]:
                client.crear_encuesta(item)
        else:
            print(f"❌ Formato no soportado por el cliente: {ruta.suffix}")
            sys.exit(1)

    else:
        print("ℹ️  Use --demo para generar datos de prueba o --file para cargar un archivo.")
        print("   Ejemplo: python client.py --demo --n 50")
        print("   Ejemplo: python client.py --file data/customer_feedback_survey.csv\n")

    # Generar reporte final
    generar_reporte(client)
    client.close()


if __name__ == "__main__":
    main()
