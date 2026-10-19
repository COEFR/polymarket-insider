#!/usr/bin/env python3
"""Baja la miniatura (arte) del mercado de Polymarket para adjuntarla a la alerta."""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (polymarket-alertas)"}


def descargar(url: str | None, salida: str) -> str | None:
    """Descarga la imagen del mercado y devuelve la ruta local (o None si no hay)."""
    if not url:
        return None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25) as r:
            datos = r.read()
        if len(datos) < 500:                     # respuesta vacía o un placeholder mínimo
            return None
        cabecera = datos[:12]
        if cabecera.startswith(b"\x89PNG"):
            ext = "png"
        elif cabecera.startswith(b"\xff\xd8"):
            ext = "jpg"
        elif cabecera[:4] == b"RIFF":
            ext = "webp"
        elif cabecera[:3] == b"GIF":
            ext = "gif"
        else:
            return None                          # no es una imagen
        ruta = str(Path(salida).with_suffix("." + ext))
        Path(ruta).parent.mkdir(parents=True, exist_ok=True)
        Path(ruta).write_bytes(datos)
        return ruta
    except Exception as e:
        print(f"! miniatura: {str(e)[:70]}")
        return None


def por_condicion(condition_id: str) -> str | None:
    """Respaldo: la imagen del mercado en la API gamma (cuando el trade no trae `icon`)."""
    if not condition_id:
        return None
    try:
        url = f"https://gamma-api.polymarket.com/markets?condition_ids={condition_id}"
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
            datos = json.loads(r.read())
        if isinstance(datos, list) and datos:
            m = datos[0]
            return m.get("image") or m.get("icon") or m.get("imageUrl")
    except Exception as e:
        print(f"! gamma: {str(e)[:60]}")
    return None


def por_evento(slug: str) -> str | None:
    """Segundo respaldo: la imagen del evento (cuando el mercado no tiene arte propio)."""
    if not slug:
        return None
    try:
        url = f"https://gamma-api.polymarket.com/events?slug={slug}"
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
            datos = json.loads(r.read())
        if isinstance(datos, list) and datos:
            e = datos[0]
            return e.get("image") or e.get("icon")
    except Exception as e:
        print(f"! gamma evento: {str(e)[:60]}")
    return None


def para_trade(trade: dict, salida: str) -> str | None:
    """Miniatura: icon del trade → imagen del mercado (gamma) → imagen del evento."""
    cid = trade.get("conditionId") or trade.get("market") or ""
    url = (trade.get("icon")
           or por_condicion(cid)
           or por_evento(trade.get("eventSlug") or trade.get("slug") or ""))
    return descargar(url, salida)
