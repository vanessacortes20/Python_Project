"""services.py"""
from __future__ import annotations
import io, json, logging, pickle, uuid
from collections import Counter
from typing import Any, Dict, List, Tuple
import numpy as np
import pandas as pd
from scipy import stats as scipy_stats
from models import AnalisisColomnaResult, CargaArchivoResult, ReporteAnalisis
from validators import es_columna_id

logger = logging.getLogger("encuesta_api.services")

class AnalizadorEncuesta:
    def __init__(self, df):
        self.df = df.copy(); self.columnas_id = []; self.columnas_analisis = []
        for col in self.df.columns:
            (self.columnas_id if es_columna_id(col, self.df[col]) else self.columnas_analisis).append(col)

    def _tipo(self, col):
        s = self.df[col]
        if pd.api.types.is_datetime64_any_dtype(s): return "fecha"
        if s.dtype == bool: return "booleana"
        if pd.api.types.is_numeric_dtype(s):
            nu, nt = s.nunique(), len(s.dropna())
            if nt == 0: return "numerica_discreta"
            return "numerica_discreta" if (nu <= 10 or nu/nt < 0.05) else "numerica_continua"
        return "categorica_nominal" if s.nunique() <= 20 else "texto_libre"

    def _normalidad(self, serie):
        v = serie.dropna()
        if len(v) < 8: return {"test":"insuficiente","estadistico":None,"p_valor":None,"es_normal":None,"conclusion":"Muestra insuficiente (<8)"}
        try:
            fn = scipy_stats.shapiro if len(v) <= 5000 else scipy_stats.normaltest
            nm = "Shapiro-Wilk" if len(v) <= 5000 else "DAgostino-Pearson"
            st, p = fn(v)
            return {"test":nm,"estadistico":round(float(st),4),"p_valor":round(float(p),4),"es_normal":bool(p>0.05),"conclusion":"Normal (p>0.05)" if p>0.05 else "No normal (p<=0.05)"}
        except Exception as e: return {"test":"error","conclusion":str(e),"es_normal":None}

    def _outliers(self, serie):
        v = serie.dropna()
        if len(v) < 4 or not pd.api.types.is_numeric_dtype(serie): return {"n_outliers":0,"pct_outliers":0}
        q1,q3 = float(v.quantile(.25)),float(v.quantile(.75)); iqr = q3-q1; li,ls = q1-1.5*iqr,q3+1.5*iqr
        oi = v[(v<li)|(v>ls)]; z = np.abs(scipy_stats.zscore(v)); oz = v[z>3]
        return {"metodo":"IQR+Z-score","n_outliers":len(oi),"n_outliers_zscore":len(oz),
                "pct_outliers":round(len(oi)/len(v)*100,2),"limite_inferior":round(li,4),
                "limite_superior":round(ls,4),"q1":round(q1,4),"q3":round(q3,4),"iqr":round(iqr,4),
                "valores_extremos":[round(float(x),4) for x in sorted(set(list(oi.values)+list(oz.values)))[:10]]}

    def _histograma(self, serie):
        v = serie.dropna()
        if len(v) < 2 or not pd.api.types.is_numeric_dtype(serie): return {}
        try:
            cnt,edges = np.histogram(v, bins=min(12,len(v.unique())))
            return {"bins":[round(float(e),3) for e in edges],"counts":[int(c) for c in cnt],
                    "labels":[f"{round(float(edges[i]),1)}-{round(float(edges[i+1]),1)}" for i in range(len(cnt))]}
        except: return {}

    def _qq(self, serie, n=60):
        v = serie.dropna()
        if len(v) < 4 or not pd.api.types.is_numeric_dtype(serie): return {}
        try:
            (osm,osr),(sl,ic,r) = scipy_stats.probplot(v, dist="norm"); step = max(1,len(osm)//n)
            return {"teoricos":[round(float(x),4) for x in osm[::step]],"observados":[round(float(x),4) for x in osr[::step]],
                    "linea_slope":round(float(sl),4),"linea_intercept":round(float(ic),4),"r_cuadrado":round(float(r**2),4)}
        except: return {}

    def _boxplot(self, serie):
        v = serie.dropna()
        if len(v) < 2 or not pd.api.types.is_numeric_dtype(serie): return {}
        try:
            q1,q3 = float(np.percentile(v,25)),float(np.percentile(v,75)); iqr = q3-q1; li,ls = q1-1.5*iqr,q3+1.5*iqr
            out = v[(v<li)|(v>ls)]
            return {"min":round(float(v.min()),4),"q1":round(q1,4),"mediana":round(float(v.median()),4),
                    "q3":round(q3,4),"max":round(float(v.max()),4),"media":round(float(v.mean()),4),
                    "outliers":[round(float(x),4) for x in out[:20]],"n_outliers":len(out)}
        except: return {}

    def analizar_columna(self, col):
        serie = self.df[col]; es_id = col in self.columnas_id; tipo = self._tipo(col)
        n_total = len(serie); n_nulos = int(serie.isna().sum())
        pct_nulos = round(n_nulos/n_total*100,2) if n_total > 0 else 0.0
        media=mediana=desv_std=minimo=maximo=skewness=kurtosis=None
        top_valores=normalidad=outliers_info=histograma=qq_datos=boxplot_datos=None
        if not es_id and pd.api.types.is_numeric_dtype(serie) and tipo != "booleana":
            v = serie.dropna()
            if len(v) > 0:
                media=round(float(v.mean()),4); mediana=round(float(v.median()),4)
                desv_std=round(float(v.std()),4) if len(v)>1 else 0.0
                minimo=round(float(v.min()),4); maximo=round(float(v.max()),4)
                if len(v) > 3:
                    skewness = round(float(scipy_stats.skew(v)),4)
                    kurtosis = round(float(scipy_stats.kurtosis(v)),4)
            normalidad=self._normalidad(serie); outliers_info=self._outliers(serie)
            histograma=self._histograma(serie); qq_datos=self._qq(serie); boxplot_datos=self._boxplot(serie)
        elif not es_id:
            top = serie.value_counts().head(8)
            top_valores = [{"valor":str(k),"frecuencia":int(v),"pct":round(int(v)/n_total*100,1)} for k,v in top.items()]
        return AnalisisColomnaResult(
            nombre=col,tipo_detectado=tipo,es_columna_id=es_id,incluida_en_calculo=not es_id,
            n_total=n_total,n_nulos=n_nulos,pct_nulos=pct_nulos,n_unicos=int(serie.nunique()),
            media=media,mediana=mediana,desv_std=desv_std,minimo=minimo,maximo=maximo,
            skewness=skewness,kurtosis=kurtosis,top_valores=top_valores,
            normalidad=normalidad,outliers=outliers_info,
            histograma=histograma,qq_datos=qq_datos,boxplot_datos=boxplot_datos)

    def detectar_patron_nulos(self):
        var = self.df.isna().sum(axis=1).var()
        if var < 0.5: return "MCAR (Missing Completely At Random)"
        if var < 2.0: return "MAR (Missing At Random)"
        return "MNAR (Missing Not At Random)"

    def recomendar_imputacion(self):
        df_a = self.df[self.columnas_analisis] if self.columnas_analisis else self.df
        pct = df_a.isna().mean().max()*100; nc = df_a.select_dtypes(include=[np.number]).shape[1]
        if pct < 5: return "Media/Mediana (nulos muy bajos)"
        if nc >= 3 and pct < 30: return "KNN Imputer (correlacion multivariada)"
        if pct < 50: return "MICE (nulos moderados)"
        return "Eliminacion casewise (>50% nulos)"

    def matriz_correlacion(self) -> Dict:
        """
        Calcula la matriz de correlación de Pearson entre variables numéricas
        (excluyendo IDs). Incluye p-valores y marca correlaciones significativas.
        """
        cols = [c for c in self.columnas_analisis
                if pd.api.types.is_numeric_dtype(self.df[c]) and self.df[c].nunique() > 2]
        if len(cols) < 2:
            return {"disponible": False, "razon": "Menos de 2 variables numéricas no-ID"}
        df_n = self.df[cols].dropna()
        if len(df_n) < 5:
            return {"disponible": False, "razon": "Insuficientes filas sin nulos"}
        corr = df_n.corr(method="pearson")
        # p-values
        pvals = {}
        for c1 in cols:
            pvals[c1] = {}
            for c2 in cols:
                if c1 == c2:
                    pvals[c1][c2] = 0.0
                else:
                    try:
                        _, p = scipy_stats.pearsonr(df_n[c1], df_n[c2])
                        pvals[c1][c2] = round(float(p), 4)
                    except Exception:
                        pvals[c1][c2] = None
        # Flatten para frontend
        pares = []
        seen = set()
        for i, c1 in enumerate(cols):
            for c2 in cols[i+1:]:
                r = round(float(corr.loc[c1, c2]), 4)
                p = pvals[c1][c2]
                sig = p is not None and p < 0.05
                pares.append({"var1": c1, "var2": c2, "r": r, "p_valor": p,
                              "significativa": sig,
                              "fuerza": "fuerte" if abs(r) >= 0.7 else "moderada" if abs(r) >= 0.4 else "débil",
                              "direccion": "positiva" if r > 0 else "negativa"})
        pares.sort(key=lambda x: abs(x["r"]), reverse=True)
        return {
            "disponible": True,
            "columnas": cols,
            "matriz": {c: {c2: round(float(corr.loc[c, c2]), 4) for c2 in cols} for c in cols},
            "pares_ordenados": pares,
            "n_significativas": sum(1 for p in pares if p["significativa"]),
        }

    def reporte_completo(self, dataset_id, nombre):
        correlacion = self.matriz_correlacion()
        return ReporteAnalisis(
            dataset_id=dataset_id, nombre_archivo=nombre,
            total_filas=len(self.df), total_columnas=len(self.df.columns),
            columnas_id_detectadas=self.columnas_id, columnas_para_analisis=self.columnas_analisis,
            columnas=[self.analizar_columna(c) for c in self.df.columns],
            patron_nulos=self.detectar_patron_nulos(), recomendacion_imputacion=self.recomendar_imputacion(),
            correlacion=correlacion)


class ImputadorInteligente:
    """Seleccion automatica del mejor metodo de imputacion por variable con criterios estadisticos."""
    def __init__(self, df, columnas_id):
        self.df_original = df.copy(); self.df = df.copy()
        self.columnas_id = columnas_id; self.decisiones = []; self.columnas_eliminadas = []

    def _norm_p(self, serie):
        v = serie.dropna()
        if len(v) < 8: return True, 1.0
        try:
            fn = scipy_stats.shapiro if len(v) <= 5000 else scipy_stats.normaltest
            _, p = fn(v); return bool(p > 0.05), round(float(p), 4)
        except: return True, 1.0

    def _corr_media(self, col, cols_num):
        otras = [c for c in cols_num if c != col and c not in self.columnas_id and c in self.df.columns]
        if not otras: return 0.0
        try:
            cs = [abs(self.df[col].corr(self.df[c])) for c in otras]
            cs = [x for x in cs if not np.isnan(x)]
            return round(float(np.mean(cs)),4) if cs else 0.0
        except: return 0.0

    def _metodo(self, col, cols_num):
        s = self.df[col]; nn = s.isna().sum(); nt = len(s); pct = nn/nt*100
        if nn == 0: return "ninguno","Sin valores faltantes"
        if pct > 60: return "eliminar",f"Exceso nulos ({pct:.1f}%>60%)"
        v = s.dropna(); nv = len(v)
        en, pn = self._norm_p(s)
        sk = float(scipy_stats.skew(v)) if nv > 3 else 0.0
        corr = self._corr_media(col, cols_num)
        nc = len([c for c in cols_num if c not in self.columnas_id and c in self.df.columns])
        if nv < 20:
            m = "mediana" if abs(sk) > 0.5 else "media"
            return m, f"Muestra pequenya (n={nv})"
        if nc >= 3 and corr >= 0.3 and pct <= 40:
            return "knn", f"Correlacion media={corr:.2f}>=0.3, {nc} vars, {pct:.1f}% nulos"
        if pct >= 15 and nc >= 2 and pct <= 50:
            return "mice", f"Nulos {pct:.1f}%, {nc} vars MICE multivariado"
        if en and abs(sk) <= 1.0:
            return "media", f"Normal (Shapiro p={pn}), skew={sk:.2f}"
        return "mediana", f"No normal (p={pn}) o asimetrica (skew={sk:.2f})"

    def imputar(self):
        cols_num = [c for c in self.df.select_dtypes(include=[np.number]).columns if c not in self.columnas_id]
        cols_cat = [c for c in self.df.select_dtypes(exclude=[np.number]).columns if c not in self.columnas_id]
        cknn, cmice = [], []
        for col in cols_num:
            met, crit = self._metodo(col, cols_num); ni = int(self.df[col].isna().sum())
            if met == "ninguno": self.decisiones.append({"columna":col,"tipo":"numerica","metodo":"ninguno","n_imputados":0,"criterio":crit})
            elif met == "eliminar":
                self.columnas_eliminadas.append(col); self.df.drop(columns=[col], inplace=True)
                self.decisiones.append({"columna":col,"tipo":"numerica","metodo":"eliminar","n_imputados":0,"criterio":crit})
            elif met == "media":
                val = self.df[col].mean(); self.df[col].fillna(val, inplace=True)
                self.decisiones.append({"columna":col,"tipo":"numerica","metodo":"media","n_imputados":ni,"valor_usado":round(float(val),4),"criterio":crit})
            elif met == "mediana":
                val = self.df[col].median(); self.df[col].fillna(val, inplace=True)
                self.decisiones.append({"columna":col,"tipo":"numerica","metodo":"mediana","n_imputados":ni,"valor_usado":round(float(val),4),"criterio":crit})
            elif met == "knn": cknn.append((col,ni,crit))
            elif met == "mice": cmice.append((col,ni,crit))
        vivos = [c for c in cols_num if c in self.df.columns]
        if cknn:
            try:
                from sklearn.impute import KNNImputer
                arr = KNNImputer(n_neighbors=5, weights="distance").fit_transform(self.df[vivos])
                self.df[vivos] = arr
                for col,ni,crit in cknn: self.decisiones.append({"columna":col,"tipo":"numerica","metodo":"knn","n_imputados":ni,"criterio":crit,"k":5})
            except ImportError:
                for col,ni,crit in cknn:
                    val = self.df[col].median() if col in self.df.columns else 0
                    if col in self.df.columns: self.df[col].fillna(val, inplace=True)
                    self.decisiones.append({"columna":col,"tipo":"numerica","metodo":"mediana (fallback KNN)","n_imputados":ni,"valor_usado":round(float(val),4),"criterio":crit})
        if cmice:
            try:
                from sklearn.experimental import enable_iterative_imputer  # noqa
                from sklearn.impute import IterativeImputer
                arr = IterativeImputer(max_iter=10, random_state=42).fit_transform(self.df[vivos])
                self.df[vivos] = arr
                for col,ni,crit in cmice: self.decisiones.append({"columna":col,"tipo":"numerica","metodo":"mice","n_imputados":ni,"criterio":crit})
            except ImportError:
                for col,ni,crit in cmice:
                    val = self.df[col].median() if col in self.df.columns else 0
                    if col in self.df.columns: self.df[col].fillna(val, inplace=True)
                    self.decisiones.append({"columna":col,"tipo":"numerica","metodo":"mediana (fallback MICE)","n_imputados":ni,"valor_usado":round(float(val),4),"criterio":crit})
        for col in cols_cat:
            if col not in self.df.columns: continue
            nn = self.df[col].isna().sum(); pct = nn/len(self.df)*100
            if nn == 0: self.decisiones.append({"columna":col,"tipo":"categorica","metodo":"ninguno","n_imputados":0,"criterio":"Sin faltantes"})
            elif pct > 50:
                self.columnas_eliminadas.append(col); self.df.drop(columns=[col], inplace=True)
                self.decisiones.append({"columna":col,"tipo":"categorica","metodo":"eliminar","n_imputados":0,"criterio":f"Exceso nulos ({pct:.1f}%)"})
            else:
                moda = self.df[col].mode()
                if len(moda) > 0:
                    self.df[col].fillna(moda[0], inplace=True)
                    self.decisiones.append({"columna":col,"tipo":"categorica","metodo":"moda","n_imputados":int(nn),"valor_usado":str(moda[0]),"criterio":f"Categorica {pct:.1f}% nulos moda"})
        return self

    def resumen(self):
        nb = int(self.df_original.isna().sum().sum()); nd = int(self.df.isna().sum().sum())
        return {"filas_originales":len(self.df_original),"filas_finales":len(self.df),
                "columnas_originales":len(self.df_original.columns),"columnas_finales":len(self.df.columns),
                "columnas_eliminadas":self.columnas_eliminadas,"nulos_antes":nb,"nulos_despues":nd,
                "reduccion_nulos_pct":round((nb-nd)/max(nb,1)*100,2),"decisiones_imputacion":self.decisiones}


def leer_archivo(contenido, nombre):
    n = nombre.lower()
    try:
        if n.endswith(".csv"): return pd.read_csv(io.BytesIO(contenido)), "csv"
        if n.endswith(".json"):
            data = json.loads(contenido)
            if isinstance(data,dict) and data.get("type") == "FeatureCollection":
                return pd.DataFrame([f.get("properties",{}) for f in data.get("features",[])]), "geojson"
            return pd.DataFrame(data if isinstance(data,list) else [data]), "json"
        if n.endswith(".geojson"):
            data = json.loads(contenido)
            return pd.DataFrame([f.get("properties",{}) for f in data.get("features",[])]), "geojson"
        if n.endswith(".shp"):
            try:
                import geopandas as gpd
                gdf = gpd.read_file(io.BytesIO(contenido))
                return pd.DataFrame(gdf.drop(columns="geometry", errors="ignore")), "shapefile"
            except ImportError: raise ValueError("Para .shp instale geopandas.")
        raise ValueError(f"Formato no soportado: {nombre}")
    except (json.JSONDecodeError, pd.errors.ParserError) as e:
        raise ValueError(f"Error parseando: {e}")


def procesar_archivo_encuesta(contenido, nombre, nombre_dataset=""):
    df, fmt = leer_archivo(contenido, nombre)
    did = str(uuid.uuid4()); ds = nombre_dataset or nombre
    analizador = AnalizadorEncuesta(df)
    reporte = analizador.reporte_completo(did, ds)
    nb = int(df.isna().sum().sum())
    imp = ImputadorInteligente(df, analizador.columnas_id)
    imp.imputar(); res = imp.resumen(); df_l = imp.df
    errores = [f"'{c}': {n} nulo(s)" for c,n in df_l.isna().sum()[df_l.isna().sum()>0].items()][:10]
    return df_l, CargaArchivoResult(
        nombre_archivo=ds, formato_detectado=fmt,
        filas_originales=res["filas_originales"], filas_validas=res["filas_finales"],
        filas_rechazadas=0, columnas_id_excluidas=analizador.columnas_id,
        columnas_analizadas=analizador.columnas_analisis,
        nulos_antes=nb, nulos_despues=res["nulos_despues"],
        metodo_imputacion="inteligente (por variable)", errores_muestra=errores), reporte, res


def calcular_estadisticas(encuestas):
    if not encuestas:
        return {"total_encuestas":0,"edad_promedio":None,"edad_mediana":None,"edad_min":None,"edad_max":None,
                "distribucion_estrato":{},"distribucion_departamento":{},"distribucion_genero":{},
                "distribucion_canal":{},"promedio_respuestas_por_encuesta":0.0,"pct_nulos_por_pregunta":{}}
    edades = [e.encuestado.edad for e in encuestas]; tr = {}
    for enc in encuestas:
        for r in enc.respuestas: tr.setdefault(r.pregunta_id,[]).append(r.valor)
    return {"total_encuestas":len(encuestas),"edad_promedio":round(float(np.mean(edades)),2),
            "edad_mediana":float(np.median(edades)),"edad_min":int(min(edades)),"edad_max":int(max(edades)),
            "distribucion_estrato":dict(Counter(str(e.encuestado.estrato) for e in encuestas)),
            "distribucion_departamento":dict(Counter(e.encuestado.departamento for e in encuestas)),
            "distribucion_genero":dict(Counter((e.encuestado.genero or "No especificado").capitalize() for e in encuestas)),
            "distribucion_canal":dict(Counter(e.canal_recoleccion or "No especificado" for e in encuestas)),
            "promedio_respuestas_por_encuesta":round(sum(len(e.respuestas) for e in encuestas)/len(encuestas),2),
            "pct_nulos_por_pregunta":{pid:round(sum(1 for v in vals if v is None)/len(vals)*100,2) for pid,vals in tr.items()}}


def exportar_json(encuestas):
    data = [json.loads(e.model_dump_json()) for e in encuestas]
    c = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"); return c, len(c)

def exportar_pickle(encuestas):
    c = pickle.dumps([e.model_dump() for e in encuestas]); return c, len(c)

def exportar_csv(encuestas) -> tuple:
    """
    Exporta encuestas a CSV aplanando la estructura anidada.
    Cada fila = una encuesta con columnas de encuestado + una columna por respuesta (pivot).
    """
    rows = []
    for enc in encuestas:
        row = {
            "id": enc.id,
            "fecha_ingreso": enc.fecha_ingreso.isoformat() if enc.fecha_ingreso else "",
            "canal_recoleccion": enc.canal_recoleccion or "",
            "nombre": enc.encuestado.nombre,
            "edad": enc.encuestado.edad,
            "genero": enc.encuestado.genero or "",
            "estrato": enc.encuestado.estrato,
            "departamento": enc.encuestado.departamento,
            "nivel_educativo": enc.encuestado.nivel_educativo or "",
        }
        for resp in enc.respuestas:
            row[f"resp_{resp.pregunta_id}_tipo"] = resp.tipo_pregunta
            row[f"resp_{resp.pregunta_id}_valor"] = resp.valor if resp.valor is not None else ""
        rows.append(row)
    if not rows:
        return b"", 0
    df = pd.DataFrame(rows)
    buf = io.StringIO()
    df.to_csv(buf, index=False, encoding="utf-8")
    c = buf.getvalue().encode("utf-8-sig")  # BOM para Excel
    return c, len(c)

def exportar_dataset_csv(df: pd.DataFrame) -> tuple:
    """Exporta un DataFrame de dataset cargado como CSV."""
    buf = io.StringIO()
    df.to_csv(buf, index=False, encoding="utf-8")
    c = buf.getvalue().encode("utf-8-sig")
    return c, len(c)
