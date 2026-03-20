"""
main.py
=======
Punto de entrada de la API REST — Gestión de Encuestas Poblacionales.
"""
from __future__ import annotations
import logging
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional
import uvicorn
from fastapi import FastAPI, File, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from models import CargaArchivoResult, EncuestaCompleta, EncuestaDB, EncuestaResumen, ErrorDetalle, ErrorResponse, EstadisticasGlobales, ReporteAnalisis
from services import calcular_estadisticas, procesar_archivo_encuesta
from validators import log_request, timer

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s", handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger("encuesta_api")

app = FastAPI(title="🗳️ API de Gestión de Encuestas Poblacionales", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

_store: Dict[str, EncuestaDB] = {}

@app.get("/", tags=["Sistema"])
async def root():
    return {"status": "online", "version": "1.0.0", "encuestas": len(_store)}
