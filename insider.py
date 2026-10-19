#!/usr/bin/env python3
"""Detector liviano de "dinero informado" en Polymarket.

No es el insider-tracker completo (ese necesita Postgres, Redis y un servicio encendido).
Esto corre en GitHub Actions: mira los trades públicos recientes y, cuando aparece una
apuesta grande, revisa la wallet. Si la wallet es nueva o casi no tiene historial, se avisa
al canal #🕵️-polymarket-insider con los datos para poder mirarlo a mano.

Fuente: API pública data-api.polymarket.com (sin claves). No opera nada.
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import uuid
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://data-api.polymarket.com"
import miniatura

ESTADO = Path(__file__).with_name("vistos.json")
STATS = Path(__file__).with_name("stats.json")
ALERTAS = Path(__file__).with_name("alertas.jsonl")
UA = {"User-Agent": "polymarket-insider/1.0"}

MIN_USD = float(os.environ.get("MIN_USD", "500"))          # apuesta mínima para mirarla
MAX_EDAD_DIAS = int(os.environ.get("MAX_EDAD_DIAS", "14"))  # wallet "nueva"
MAX_TRADES = int(os.environ.get("MAX_TRADES", "25"))        # historial corto
INTERVALO = int(os.environ.get("INTERVALO", "60"))


def traer(url: str, timeout: int = 20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def trades_recientes(limite: int = 100) -> list:
    try:
        datos = traer(f"{API}/trades?limit={limite}")
        return datos if isinstance(datos, list) else []
    except Exception as e:
        print(f"! trades: {str(e)[:80]}")
        return []


_perfil_cache: dict = {}


def perfil(wallet: str) -> dict:
    """Edad, cantidad de operaciones y valor en juego de la wallet."""
    if wallet in _perfil_cache:
        return _perfil_cache[wallet]
    datos = {"edad_dias": None, "trades": None, "valor": None}
    try:
        suyos = traer(f"{API}/trades?user={urllib.parse.quote(wallet)}&limit=500")
        if isinstance(suyos, list) and suyos:
            datos["trades"] = len(suyos)
            primera = min(int(t["timestamp"]) for t in suyos)
            datos["edad_dias"] = round((time.time() - primera) / 86400, 1)
    except Exception as e:
        print(f"! perfil trades: {str(e)[:60]}")
    try:
        valor = traer(f"{API}/value?user={urllib.parse.quote(wallet)}")
        if isinstance(valor, list) and valor:
            datos["valor"] = round(float(valor[0].get("value") or 0), 2)
    except Exception:
        pass
    _perfil_cache[wallet] = datos
    return datos


def puntuar(trade: dict, p: dict) -> tuple[int, list]:
    """Puntaje 0-6 de 'esto huele a información'."""
    usd = float(trade.get("size") or 0) * float(trade.get("price") or 0)
    precio = float(trade.get("price") or 0)
    puntos, motivos = 0, []
    edad, n, valor = p.get("edad_dias"), p.get("trades"), p.get("valor")

    if edad is not None:
        if edad <= 3:
            puntos += 2; motivos.append(f"wallet de {edad:g} días")
        elif edad <= MAX_EDAD_DIAS:
            puntos += 1; motivos.append(f"wallet de {edad:g} días")
    if n is not None and n <= MAX_TRADES:
        puntos += 1; motivos.append(f"solo {n} operaciones")
    if usd >= 2000:
        puntos += 2; motivos.append(f"apuesta de ${usd:,.0f}")
    elif usd >= MIN_USD:
        puntos += 1; motivos.append(f"apuesta de ${usd:,.0f}")
    if precio <= 0.15 or precio >= 0.85:
        puntos += 1; motivos.append(f"precio extremo {precio:.2f}")
    if valor and valor >= 10_000:
        puntos += 1; motivos.append(f"${valor:,.0f} en juego")
    return puntos, motivos


def enlaces(trade: dict) -> str:
    slug = trade.get("eventSlug") or trade.get("slug") or ""
    wallet = trade.get("proxyWallet") or ""
    poly = f"https://polymarket.com/event/{slug}" if slug else "https://polymarket.com"
    perfil = f"https://polymarket.com/profile/{wallet}" if wallet else ""
    linea = f"[Polymarket]({poly})"
    if perfil:
        linea += f" · [Perfil]({perfil})"
    return "🔗 Links\n" + linea


def formato(trade: dict, p: dict, puntos: int, motivos: list) -> str:
    usd = float(trade.get("size") or 0) * float(trade.get("price") or 0)
    wallet = trade.get("proxyWallet") or ""
    cuando = datetime.fromtimestamp(int(trade.get("timestamp") or time.time()), timezone.utc)
    cuando = cuando.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        f"🕵️ **DINERO INFORMADO?** · {puntos}/6\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📡 Mercado: {trade.get('title') or '—'}\n"
        f"🎯 {trade.get('outcome') or trade.get('side')} · **${usd:,.0f}** a {float(trade.get('price') or 0):.3f}\n"
        f"👛 `{wallet[:6]}…{wallet[-4:]}`"
        + (f" · {p['edad_dias']:g} días" if p.get("edad_dias") is not None else "")
        + (f" · {p['trades']} ops" if p.get("trades") is not None else "")
        + (f" · ${p['valor']:,.0f} en juego" if p.get("valor") else "")
        + f"\n🧩 {', '.join(motivos)}\n"
        f"🕐 {cuando}\n"
        f"{enlaces(trade)}"
    )


def _multipart(payload: dict, imagen: str) -> tuple[bytes, str]:
    b = "----poly" + uuid.uuid4().hex
    partes = [f"--{b}\r\nContent-Disposition: form-data; name=\"payload_json\"\r\n\r\n"
              f"{json.dumps(payload)}\r\n".encode()]
    with open(imagen, "rb") as fh:
        partes.append(f"--{b}\r\nContent-Disposition: form-data; name=\"files[0]\"; "
                      f"filename=\"miniatura.png\"\r\nContent-Type: image/png\r\n\r\n".encode()
                      + fh.read() + b"\r\n")
    partes.append(f"--{b}--\r\n".encode())
    return b"".join(partes), f"multipart/form-data; boundary={b}"


def enviar(texto: str, imagen: str | None = None) -> bool:
    token = os.environ.get("DISCORD_BOT_TOKEN", "")
    canal = os.environ.get("DISCORD_CHANNEL", "")
    if not token or not canal:
        print("(sin token/canal: esto habría enviado)\n" + texto)
        return False
    payload = {"content": texto[:1900], "flags": 4}
    if imagen and os.path.exists(imagen):
        datos, ctype = _multipart(payload, imagen)
    else:
        datos, ctype = json.dumps(payload).encode(), "application/json"
    req = urllib.request.Request(
        f"https://discord.com/api/v10/channels/{canal}/messages", data=datos,
        headers={"Authorization": f"Bot {token}", "Content-Type": ctype, **UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status in (200, 204)
    except Exception as e:
        print(f"! discord: {str(e)[:80]}")
        return False


def cargar_vistos() -> set:
    try:
        return set(json.loads(ESTADO.read_text()))
    except Exception:
        return set()


def guardar_vistos(ids: set) -> None:
    try:
        tmp = ESTADO.with_suffix(".tmp")
        tmp.write_text(json.dumps(sorted(ids)[-4000:]))
        tmp.replace(ESTADO)
    except Exception as e:
        print(f"! estado: {str(e)[:60]}")


def clave(t: dict) -> str:
    return f"{t.get('proxyWallet')}-{t.get('timestamp')}-{t.get('asset')}-{t.get('size')}-{t.get('price')}"


def _hoy() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def cargar_stats() -> dict:
    try:
        d = json.loads(STATS.read_text())
        if d.get("fecha") == _hoy():
            return d
    except Exception:
        pass
    return {"fecha": _hoy(), "revisados": 0, "candidatos": 0, "alertas": 0}


def guardar_stats(d: dict) -> None:
    try:
        STATS.write_text(json.dumps(d))
    except Exception:
        pass


def resumen() -> int:
    """Resumen del día: cuántos trades se revisaron, cuántos candidatos y cuáles avisaron."""
    st = cargar_stats()
    alertas = []
    try:
        for ln in ALERTAS.read_text().splitlines()[-50:]:
            a = json.loads(ln)
            if a.get("fecha") == st["fecha"]:
                alertas.append(a)
    except Exception:
        pass
    if alertas:
        cuerpo = f"🕵️ **Resumen del día** · {st['candidatos']} candidatos de {st['revisados']} trades\n"
        for a in alertas[-5:]:
            cuerpo += (f"· {a['wallet'][:6]}…{a['wallet'][-4:]} · ${a['usd']:,.0f} "
                       f"{a['outcome']} · {a['puntos']}/6 · {a['mercado'][:45]}\n")
    else:
        cuerpo = (f"🕵️ **Resumen del día**: sin candidatos que pasen el filtro\n"
                  f"Revisé {st['revisados']} trades · {st['candidatos']} candidatos con apuesta grande\n")
    enviar(cuerpo + "🔗 Links\n[Polymarket](https://polymarket.com)")
    return 0


def main() -> int:
    if "--resumen" in os.sys.argv:
        return resumen()
    vistos = cargar_vistos()
    stats = cargar_stats()
    inicio = time.time()
    print(f"inicio · min ${MIN_USD:.0f} · estado {len(vistos)} vistos")
    while time.time() - inicio < 260:
        trades = trades_recientes(100)
        nuevos = [t for t in trades if clave(t) not in vistos]
        for t in nuevos:
            vistos.add(clave(t))
        alertas = 0
        stats["revisados"] += len(nuevos)
        for t in nuevos:
            usd = float(t.get("size") or 0) * float(t.get("price") or 0)
            if usd < MIN_USD:
                continue
            stats["candidatos"] += 1
            p = perfil(t.get("proxyWallet") or "")
            n = p.get("trades")
            # una wallet con cientos de operaciones es un profesional (o un bot), no alguien
            # con información: no se avisa, salvo que la apuesta sea enorme.
            if n is not None and n > MAX_TRADES and usd < 5000:
                continue
            puntos, motivos = puntuar(t, p)
            if n is not None and n > MAX_TRADES:
                puntos -= 2
            if puntos < 3:
                continue
            try:
                png = miniatura.para_trade(t, str(Path(__file__).with_name("charts") / f"pm_{int(time.time())}.png"))
            except Exception as e:
                print(f"! miniatura: {str(e)[:60]}")
                png = None
            if enviar(formato(t, p, puntos, motivos), png):
                alertas += 1
                stats["alertas"] += 1
                try:
                    with open(ALERTAS, "a") as fh:
                        fh.write(json.dumps({"fecha": _hoy(), "wallet": t.get("proxyWallet") or "",
                                             "mercado": t.get("title") or "", "outcome": t.get("outcome") or "",
                                             "usd": round(usd, 2), "puntos": puntos}) + "\n")
                except Exception:
                    pass
                print(f"alerta {puntos}/6 · {t.get('title')[:40]} · ${usd:,.0f}")
            time.sleep(1.2)
        guardar_vistos(vistos)
        guardar_stats(stats)
        print(f"{datetime.now(timezone.utc):%H:%M:%S} nuevos {len(nuevos)} · alertas {alertas} · vistos {len(vistos)}")
        time.sleep(INTERVALO)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
