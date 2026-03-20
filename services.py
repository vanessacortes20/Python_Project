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
        cols = [c for c in self.columnas_analisis
                if pd.api.types.is_numeric_dtype(self.df[c]) and self.df[c].nunique() > 2]
        if len(cols) < 2:
            return {"disponible": False, "razon": "Menos de 2 variables numéricas no-ID"}
        df_n = self.df[cols].dropna()
        if len(df_n) < 5:
            return {"disponible": False, "razon": "Insuficientes filas sin nulos"}
        corr = df_n.corr(method="pearson")
        pvals = {}
        for c1 in cols:
            pvals[c1] = {}
            for c2 in cols:
                if c1 == c2: pvals[c1][c2] = 0.0
                else:
                    try:
                        _, p = scipy_stats.pearsonr(df_n[c1], df_n[c2])
                        pvals[c1][c2] = round(float(p), 4)
                    except Exception: pvals[c1][c2] = None
        pares = []
        for i, c1 in enumerate(cols):
            for c2 in cols[i+1:]:
                r = round(float(corr.loc[c1, c2]), 4)
                p = pvals[c1][c2]; sig = p is not None and p < 0.05
                pares.append({"var1": c1, "var2": c2, "r": r, "p_valor": p, "significativa": sig,
                              "fuerza": "fuerte" if abs(r) >= 0.7 else "moderada" if abs(r) >= 0.4 else "débil",
                              "direccion": "positiva" if r > 0 else "negativa"})
        pares.sort(key=lambda x: abs(x["r"]), reverse=True)
        return {"disponible": True, "columnas": cols, "matriz": {c: {c2: round(float(corr.loc[c, c2]), 4) for c2 in cols} for c in cols}, "pares_ordenados": pares, "n_significativas": sum(1 for p in pares if p["significativa"])}

    def reporte_completo(self, dataset_id, nombre):
        correlacion = self.matriz_correlacion()
        return ReporteAnalisis(
            dataset_id=dataset_id, nombre_archivo=nombre,
            total_filas=len(self.df), total_columnas=len(self.df.columns),
            columnas_id_detectadas=self.columnas_id, columnas_para_analisis=self.columnas_analisis,
            columnas=[self.analizar_columna(c) for c in self.df.columns],
            patron_nulos=self.detectar_patron_nulos(), recomendacion_imputacion=self.recomendar_imputacion(),
            correlacion=correlacion)
