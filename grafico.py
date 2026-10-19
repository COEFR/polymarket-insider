#!/usr/bin/env python3
"""Mini gráfico del mercado para adjuntar a cada alerta de Polymarket.

Toma el histórico de precios público del CLOB (`prices-history`) y dibuja una línea con
el punto de la apuesta marcado. Sin dependencias raras: Pillow y listo.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw

CLOB = "https://clob.polymarket.com/prices-history"
UA = {"User-Agent": "polymarket-alertas/1.0"}
FONDO, GRILLA, TEXTO, AMBAR, ROJO = (19, 23, 34), (35, 40, 52), (209, 212, 220), (245, 179, 1), (239, 83, 80)


def historial(token_id: str, intervalo: str = "1d", fidelidad: int = 60) -> list:
    url = f"{CLOB}?market={urllib.parse.quote(str(token_id))}&interval={intervalo}&fidelity={fidelidad}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
            datos = json.loads(r.read())
        return [(int(p["t"]), float(p["p"])) for p in datos.get("history", [])]
    except Exception as e:
        print(f"! historial: {str(e)[:70]}")
        return []


def dibujar(puntos: list, titulo: str, precio: float | None = None, salida: str = "grafico.png",
            ancho: int = 900, alto: int = 420) -> str | None:
    """Dibuja la serie y devuelve la ruta del PNG (o None si no hay datos)."""
    if len(puntos) < 3:
        return None
    img = Image.new("RGB", (ancho, alto), FONDO)
    d = ImageDraw.Draw(img)
    izq, der, arriba, abajo = 60, ancho - 20, 70, alto - 45

    ys = [p for _, p in puntos]
    ymin, ymax = min(ys), max(ys)
    if ymax - ymin < 0.02:
        medio = (ymax + ymin) / 2
        ymin, ymax = medio - 0.01, medio + 0.01
    x0, x1 = puntos[0][0], puntos[-1][0] or 1

    def px(t):
        return izq + (t - x0) / max(1, (x1 - x0)) * (der - izq)

    def py(v):
        return abajo - (v - ymin) / (ymax - ymin) * (abajo - arriba)

    # grilla y etiquetas de precio
    for i in range(4):
        v = ymin + (ymax - ymin) * i / 3
        y = py(v)
        d.line([(izq, y), (der, y)], fill=GRILLA, width=1)
        d.text((8, y - 6), f"{v * 100:4.0f}%", fill=TEXTO)

    # serie
    d.line([(px(t), py(v)) for t, v in puntos], fill=AMBAR, width=3, joint="curve")

    # punto de la apuesta
    if precio is not None:
        d.line([(izq, py(precio)), (der, py(precio))], fill=ROJO, width=1)
        d.ellipse([der - 7, py(precio) - 7, der + 7, py(precio) + 7], outline=ROJO, width=3)
        d.text((der - 150, py(precio) - 20), f"apuesta {precio * 100:.1f}%", fill=ROJO)

    # título y pie
    titulo = (titulo or "")[:95]
    d.text((izq, 16), titulo, fill=TEXTO)
    d.text((izq, 36), f"probabilidad · últimas 24 h · mín {ymin * 100:.0f}% / máx {ymax * 100:.0f}%", fill=(120, 124, 134))
    d.text((izq, alto - 30), "Fuente: Polymarket · prices-history", fill=(110, 114, 124))

    Path(salida).parent.mkdir(parents=True, exist_ok=True)
    img.save(salida, "PNG")
    return salida


def para_trade(trade: dict, salida: str = "grafico.png") -> str | None:
    """Atajo: saca el token y el precio del trade y arma el PNG."""
    token = trade.get("asset") or trade.get("tokenId") or ""
    if not token:
        return None
    puntos = historial(token)
    precio = float(trade.get("price") or 0) or None
    return dibujar(puntos, trade.get("title") or "Polymarket", precio, salida)


if __name__ == "__main__":
    t = {"asset": "42540064588474984309098065010968124137315195387045560256032749423193862593675",
         "title": "Will Su Chiao-hui win the next New Taipei Mayor election?", "price": 0.68}
    print(para_trade(t, "/home/ubuntu/.hermes/cache/scratch/grafico_pm.png"))
