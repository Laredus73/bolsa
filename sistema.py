#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SISTEMA SEMANAL DE BOLSA — version autonoma (corre solo en GitHub Actions)
==========================================================================
Universo: S&P 500 + S&P 400 (USA) + 7 indices europeos + Nikkei 225 (Japon).
Genera dos listas y las escribe en informe.html (legible, sin codigo a la vista).

LISTA A (tendencia, meses): momentum fuerte + analistas a favor, max 4/sector.
LISTA B (rebote, dias): sobrevendidas que los analistas aun respaldan.

Factores: momentum 12-1 y 6m, recorrido a objetivo con precio de hoy,
consenso de analistas, revisiones de BPA, PEG, calidad. Ranking relativo,
NO probabilidad. No es asesoramiento financiero.
"""

import sys, io, time, datetime
import requests
import yfinance as yf
import pandas as pd
import numpy as np

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"}
MIN_ANALISTAS = 8
SEC = {"Technology": "Tecnologia", "Industrials": "Industria",
       "Basic Materials": "Materias primas", "Energy": "Energia",
       "Utilities": "Electricas", "Financial Services": "Banca y finanzas",
       "Real Estate": "Inmobiliario", "Consumer Cyclical": "Consumo ciclico",
       "Consumer Defensive": "Consumo basico", "Healthcare": "Salud",
       "Communication Services": "Medios y telecos"}


def tabs(u):
    return pd.read_html(io.StringIO(requests.get(u, headers=H, timeout=40).text))


def universo():
    reg = {}
    us = []
    for u in ["https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
              "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies"]:
        try:
            for t in tabs(u):
                c = [x for x in t.columns if "ymbol" in str(x)]
                if c and len(t) > 100:
                    us += [str(x).strip().upper().replace(".", "-")
                           for x in t[c[0]] if str(x) != "nan"]
                    break
        except Exception as e:
            print("USA", e)
    eu = []
    E = {"https://en.wikipedia.org/wiki/IBEX_35": ".MC",
         "https://en.wikipedia.org/wiki/DAX": ".DE",
         "https://en.wikipedia.org/wiki/CAC_40": ".PA",
         "https://en.wikipedia.org/wiki/FTSE_100_Index": ".L",
         "https://en.wikipedia.org/wiki/FTSE_MIB": ".MI",
         "https://en.wikipedia.org/wiki/AEX_index": ".AS",
         "https://en.wikipedia.org/wiki/Swiss_Market_Index": ".SW"}
    for w, s in E.items():
        try:
            for t in tabs(w):
                c = [x for x in t.columns if "icker" in str(x)
                     or "ymbol" in str(x) or "EPIC" in str(x)]
                if c and len(t) > 17:
                    for x in t[c[0]].astype(str):
                        x = x.strip().upper().replace(" ", "-")
                        if s == ".L":
                            x = x.replace(".", "-")
                        elif "." in x:
                            x = x.split(".")[0]
                        eu.append(x if x.endswith(s) else x + s)
                    break
        except Exception as e:
            print("EU", e)
    jp = []
    for u in ["https://topforeignstocks.com/indices/"
              "the-components-of-the-nikkei-225-index/"]:
        try:
            for t in tabs(u):
                c = [x for x in t.columns
                     if str(x).strip().lower().startswith(("code", "ticker", "symbol"))]
                if c and len(t) > 80:
                    jp = [str(x).strip().split(".")[0] + ".T"
                          for x in t[c[0]] if str(x)[0].isdigit()]
                    break
            if jp:
                break
        except Exception as e:
            print("JP", e)
    for x in us:
        reg[x] = "USA"
    for x in eu:
        reg[x] = "Europa"
    for x in jp:
        reg[x] = "Japon"
    return sorted(set(us + eu + jp)), reg


def cierre(px):
    if isinstance(px.columns, pd.MultiIndex):
        n0 = px.columns.get_level_values(0)
        return px.xs("Close" if "Close" in n0 else n0[0], axis=1, level=0)
    return px


def descargar_precios(T):
    """Descarga en lotes pequenos con reintentos y normaliza cada lote a
    columnas = tickers, para que ningun mercado se pierda al concatenar."""
    frames = []
    lote = 100
    for i in range(0, len(T), lote):
        grupo = T[i:i + lote]
        d = None
        for intento in range(3):
            try:
                d = yf.download(grupo, period="13mo", auto_adjust=True,
                                progress=False, threads=True)
                if d is not None and not d.empty:
                    break
            except Exception as e:
                print(f"  lote {i} intento {intento}: {e}")
                time.sleep(4)
        if d is None or d.empty:
            print(f"  lote {i}: sin datos, se omite")
            continue
        d = cierre(d)
        # si el lote traia un solo ticker, cierre() puede devolver Serie
        if isinstance(d, pd.Series):
            d = d.to_frame(name=grupo[0])
        frames.append(d)
        print(f"  lote {i}: {d.shape[1]} valores ok")
    if not frames:
        sys.exit("ERROR: no se pudieron descargar precios (Yahoo no responde).")
    px = pd.concat(frames, axis=1)
    px = px.loc[:, ~px.columns.duplicated()]
    print(f"  TOTAL descargado: {px.shape[1]} valores")
    return px


def main():
    print("Descargando universo...")
    T, reg = universo()
    print(len(T), "valores")
    px = descargar_precios(T).dropna(axis=1, thresh=200)
    ult = px.iloc[-1]
    m12 = (px.iloc[-22] / px.iloc[0] - 1) * 100
    m6 = (ult / px.iloc[-126] - 1) * 100
    dd = px.diff()
    gg = dd.clip(lower=0).rolling(14).mean().iloc[-1]
    ll = (-dd.clip(upper=0)).rolling(14).mean().iloc[-1]
    rsi = 100 - 100 / (1 + gg / ll)
    B = pd.DataFrame({"m12": m12, "m6": m6, "rsi": rsi,
                      "dmin": (ult / px.min() - 1) * 100}).dropna()
    comp = B.m12.rank(pct=True) * .7 + B.m6.rank(pct=True) * .3
    fA = comp.nlargest(90).index.tolist()
    fB = B[(B.rsi < 35) & (B.dmin < 15)].sort_values("rsi").index.tolist()[:45]
    R = []
    for t in sorted(set(fA + fB)):
        inf = {}
        for _ in range(3):
            try:
                inf = yf.Ticker(t).info or {}
                if inf.get("numberOfAnalystOpinions") is not None or inf.get("longName"):
                    break
            except Exception:
                pass
            time.sleep(1.2)
        o = inf.get("targetMeanPrice")
        pr = float(ult[t])
        sc = inf.get("sector", "")
        eps_f, eps_t = inf.get("forwardEps"), inf.get("trailingEps")
        rev = ((eps_f / eps_t - 1) * 100
               if eps_f and eps_t and eps_t > 0 else np.nan)
        R.append(dict(tk=t, reg=reg.get(t, "?"),
                      nombre=str(inf.get("longName") or t)[:40],
                      sector=SEC.get(sc, sc or "Otros"),
                      mon=inf.get("currency", "?"), precio=round(pr, 2),
                      obj=o, rec=(o / pr - 1) * 100 if o else np.nan,
                      na=inf.get("numberOfAnalystOpinions") or 0,
                      rm=inf.get("recommendationMean") or 9, revision=rev))
        time.sleep(0.5)
    D = pd.DataFrame(R).set_index("tk").join(B)

    A = D[(D.index.isin(fA)) & (D.na >= MIN_ANALISTAS) & (D.rec.fillna(-1) > 0)].copy()
    A["SC"] = (A.m12.rank(pct=True) * 40 + A.rec.rank(pct=True) * 35
               + (6 - A.rm).rank(pct=True) * 25).round(1)
    A = A.sort_values("SC", ascending=False).groupby("sector",
                                                      group_keys=False).head(4).head(10)
    Bb = D[(D.index.isin(fB)) & (D.na >= MIN_ANALISTAS)
           & (D.rm <= 2.5) & (D.rec.fillna(0) > 20)].copy()
    if len(Bb):
        Bb["SC"] = ((100 - Bb.rsi).rank(pct=True) * 50
                    + Bb.rec.rank(pct=True) * 50).round(1)
        Bb = Bb.sort_values("SC", ascending=False).groupby("sector",
                                                           group_keys=False).head(3).head(10)
    escribir_html(A, Bb)
    print("informe.html generado")


def fila_html(i, r, modo):
    mon = str(r["mon"])
    pen = " (peniques /100)" if mon == "GBp" else ""
    obj = (f"{r['obj']:.2f} (+{r['rec']:.0f}%)"
           if r["obj"] == r["obj"] else "s/d")
    extra = (f"6 meses: {r['m6']:.0f}%"
             if modo == "A" else f"RSI {r['rsi']:.0f} (sobreventa)")
    return f"""<tr><td class=n>{i}</td><td><b>{r['nombre']}</b><br>
    <span class=tk>{r.name}</span> · {r['reg']} · {r['sector']}</td>
    <td>{r['precio']} {mon}{pen}</td><td>{obj}</td>
    <td>{int(r['na'])}</td><td>{extra}</td>
    <td class=sc>{r['SC']}</td></tr>"""


def escribir_html(A, Bb):
    fecha = datetime.date.today().strftime("%d/%m/%Y")
    filasA = "\n".join(fila_html(i + 1, r, "A")
                       for i, (_, r) in enumerate(A.iterrows()))
    if len(Bb):
        filasB = "\n".join(fila_html(i + 1, r, "B")
                           for i, (_, r) in enumerate(Bb.iterrows()))
    else:
        filasB = ("<tr><td colspan=7>Hoy ninguna empresa pasa los "
                  "filtros de calidad. Esta semana no se opera la lista B.</td></tr>")
    html = f"""<!doctype html><html lang=es><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Listas de bolsa · {fecha}</title>
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:900px;
margin:0 auto;padding:20px;color:#1a1a1a;background:#fafafa}}
h1{{font-size:22px}}h2{{font-size:18px;margin-top:32px;padding:8px 12px;border-radius:8px}}
.a h2{{background:#e8f4ea;color:#1a6b2e}}.b h2{{background:#fdeaea;color:#a11}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:8px;
overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
td{{padding:10px 8px;border-bottom:1px solid #eee;font-size:14px;vertical-align:top}}
.n{{font-weight:700;color:#999;width:24px}}.tk{{font-family:monospace;
background:#f0f0f0;padding:1px 5px;border-radius:4px;font-weight:700}}
.sc{{font-weight:700;font-size:16px}}
th{{text-align:left;padding:8px;font-size:12px;color:#888;text-transform:uppercase}}
.nota{{font-size:13px;color:#666;background:#fff;padding:12px;border-radius:8px;margin-top:12px}}
</style>
<h1>Listas de bolsa — {fecha}</h1>
<div class=a><h2>LISTA A · Comprar y mantener (meses)</h2>
<table><tr><th>#</th><th>Empresa</th><th>Precio</th><th>Objetivo</th>
<th>Analistas</th><th>Impulso</th><th>Nota</th></tr>
{filasA}</table>
<div class=nota>Empresas que suben con fuerza y que los analistas ven baratas.
Maximo 4 por sector. Comprar con orden limitada, sin perseguir el precio.</div></div>
<div class=b><h2>LISTA B · Operaciones de dias — ALTO RIESGO</h2>
<table><tr><th>#</th><th>Empresa</th><th>Precio</th><th>Objetivo</th>
<th>Analistas</th><th>Sobreventa</th><th>Nota</th></tr>
{filasB}</table>
<div class=nota>Empresas hundidas que los analistas aun respaldan. Decide el
precio de venta ANTES de comprar. Dinero pequeno.</div></div>
<div class=nota style=margin-top:24px>Ranking con indicadores objetivos,
NO es una prediccion ni asesoramiento financiero. Precios del cierre mas
reciente. Codigos europeos: busca por nombre en tu broker y confirma pais.</div>
</html>"""
    with open("informe.html", "w", encoding="utf-8") as f:
        f.write(html)


if __name__ == "__main__":
    main()
