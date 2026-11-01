# jimmi_cursor.py — Gestión Jimmi (Grok/xAI o Cursor SDK) con jobs asíncronos
import json
import os
import re
import threading
import urllib.error
import urllib.request
import uuid
from datetime import datetime

from database import get_connection, fila_a_dict

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


def _env(nombre, default=""):
    return (os.environ.get(nombre) or default).strip()


def _grok_key():
    return _env("GROK_API_KEY") or _env("XAI_API_KEY")


def _cursor_key():
    return _env("CURSOR_API_KEY")


def _grok_model():
    return _env("GROK_MODEL") or _env("XAI_MODEL") or "grok-3-mini"


def _cursor_model():
    return _env("CURSOR_AGENT_MODEL") or "composer-2.5"


def _faenas_url():
    return (
        _env("FAENAS_PUBLIC_URL")
        or _env("PUBLIC_BASE_URL")
        or _env("RENDER_EXTERNAL_URL")
    ).rstrip("/")


def gestion_disponible():
    return bool(_grok_key() or _cursor_key())


# Compatibilidad con imports antiguos
def cursor_disponible():
    return gestion_disponible()


def _ahora():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _crear_job_db(job_id, pregunta, faena_id, modo):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO jimmi_jobs (id, status, pregunta, faena_id, modo, resultado_json, error, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (job_id, "pending", pregunta or "", int(faena_id or 0), modo or "todo", "", "", _ahora(), _ahora()),
        )
        conn.commit()
    finally:
        conn.close()


def _actualizar_job(job_id, status, resultado=None, error=""):
    conn = get_connection()
    try:
        payload = json.dumps(resultado, ensure_ascii=False) if resultado is not None else ""
        conn.execute(
            "UPDATE jimmi_jobs SET status=?, resultado_json=?, error=?, updated_at=? WHERE id=?",
            (status, payload, (error or "")[:1900], _ahora(), job_id),
        )
        conn.commit()
    finally:
        conn.close()


def obtener_job(job_id):
    conn = get_connection()
    try:
        fila = conn.execute("SELECT * FROM jimmi_jobs WHERE id=?", (job_id,)).fetchone()
        if not fila:
            return None
        d = fila_a_dict(fila)
        resultado = {}
        raw = d.get("resultado_json") or ""
        if raw:
            try:
                resultado = json.loads(raw)
            except Exception:
                resultado = {"respuesta": raw}
        return {
            "id": d.get("id"),
            "status": d.get("status") or "pending",
            "pregunta": d.get("pregunta") or "",
            "faena_id": d.get("faena_id") or 0,
            "modo": d.get("modo") or "todo",
            "resultado": resultado,
            "error": d.get("error") or "",
            "created_at": d.get("created_at"),
            "updated_at": d.get("updated_at"),
        }
    finally:
        conn.close()


def _contexto_gestion(pregunta, faena_id=None, modo="todo", historial=None):
    from secretario import snapshot_negocio, memoria_para_modo
    datos = snapshot_negocio(faena_id, modo, pregunta=pregunta, historial=historial, ligero=True)
    return {
        "pregunta": pregunta,
        "faena_id": faena_id,
        "modo": modo,
        "memoria_jimmi": memoria_para_modo(modo),
        "datos_app": datos,
        "api_base": f"{_faenas_url()}/api" if _faenas_url() else "/api",
    }


def _extraer_json_bloque(texto):
    if not texto:
        return None
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", texto)
    bruto = m.group(1) if m else None
    if not bruto:
        m2 = re.search(r"(\{[\s\S]*\"propuestas\"[\s\S]*\})", texto)
        bruto = m2.group(1) if m2 else None
    if not bruto:
        return None
    try:
        return json.loads(bruto)
    except Exception:
        return None


def texto_sin_json(texto):
    if not texto:
        return ""
    return re.sub(r"```(?:json)?[\s\S]*?```", "", texto).strip()


def _system_gestion():
    return (
        "Eres Jimmi, secretario de un taller de carpintería. Hablas español, claro y breve. "
        "Ayudas a CONSULTAR y GESTIONAR la app Faenas. "
        "No inventes faenas, precios ni IDs. Usa solo datos_app del contexto. "
        "No borres faenas ni clientes. "
        "Si la petición implica cambios (anotación, gasto, cobro, línea de presupuesto, material), "
        "NO digas que ya está guardado: propone acciones en JSON para que el usuario confirme en la app. "
        "Responde con texto útil al usuario y, si hay cambios propuestos, un bloque ```json "
        "con {\"respuesta\":\"...\",\"propuestas\":[{\"tipo\":\"anotacion|gasto|cobro|presupuesto|material\","
        "\"faena_id\":n,\"descripcion\":\"...\",\"importe\":0,\"contenido\":\"...\",\"cantidad\":1,\"precio_unitario\":0}]}. "
        "tipo anotacion usa contenido; gasto/cobro usan importe y descripcion/nota; presupuesto usa descripcion, cantidad, precio_unitario. "
        "Si conoces el id de faena en datos_app, úsalo en faena_id."
    )


def _ejecutar_agente_grok(pregunta, contexto):
    key = _grok_key()
    if not key:
        raise RuntimeError("Falta GROK_API_KEY")
    modelo = _grok_model()
    user = (
        "Contexto de la app (JSON):\n"
        + json.dumps(contexto, ensure_ascii=False)[:100000]
        + "\n\nPetición del usuario:\n"
        + (pregunta or "")
    )
    body = {
        "model": modelo,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": _system_gestion()},
            {"role": "user", "content": user},
        ],
    }
    req = urllib.request.Request(
        "https://api.x.ai/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            raw = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Grok HTTP {e.code}: {detalle}") from e
    choices = raw.get("choices") or []
    texto = ""
    if choices:
        msg = (choices[0] or {}).get("message") or {}
        texto = (msg.get("content") or "").strip()
    if not texto:
        raise RuntimeError("Grok no devolvió texto")
    parsed = _extraer_json_bloque(texto) or {}
    respuesta = (parsed.get("respuesta") or "").strip() or texto_sin_json(texto)
    propuestas = parsed.get("propuestas") if isinstance(parsed.get("propuestas"), list) else []
    return {
        "respuesta": respuesta or "Listo. Revisa las propuestas si las hay.",
        "propuestas": propuestas,
        "motor": "grok",
        "modelo": modelo,
        "run_id": "",
    }


def _mensaje_error_cursor(msg):
    low = (msg or "").lower()
    if "prepaid" in low or "add funds" in low or "auto top-up" in low or "top up" in low:
        return (
            "Cursor: el saldo prepago está a 0. "
            "Añade crédito o activa Auto Top-up en Billing y reintenta."
        )
    if "additional usage is off" in low:
        return (
            "Cursor: el uso extra está desactivado. "
            "Actívalo en Settings → Billing (Additional usage) y reintenta."
        )
    if "usage_limit" in low or "spend limit" in low:
        return (
            "Cursor: límite de uso/gasto alcanzado. "
            "Sube el tope, añade crédito o espera al reset semanal del cupo."
        )
    if "api_key" in low or "unauthorized" in low or "authentication" in low:
        return "CURSOR_API_KEY inválida o sin permiso. Crea otra en Cursor → Settings → API Keys."
    return f"Cursor SDK: {msg}"


def _ejecutar_agente_cursor(pregunta, contexto):
    """Lanza un cloud agent vía cursor-sdk.

    En Windows el cliente sync del SDK falla (WinError 10038 al arrancar el bridge);
    usamos siempre la API async, que sí funciona en nativo.
    """
    key = _cursor_key()
    if not key:
        raise RuntimeError("Falta CURSOR_API_KEY en el servidor")
    try:
        import asyncio
        from cursor_sdk import AgentOptions, CloudAgentOptions
        from cursor_sdk.asyncio import AsyncAgent, AsyncClient
    except Exception as e:
        raise RuntimeError(f"cursor-sdk no disponible: {e}") from e

    modelo = _cursor_model()
    mensaje = (
        _system_gestion()
        + "\n\nContexto de la app (JSON):\n"
        + json.dumps(contexto, ensure_ascii=False)[:120000]
        + "\n\nPetición del usuario:\n"
        + (pregunta or "")
    )
    cloud_kwargs = {"repos": []}
    repo = _env("CURSOR_REPO_URL")
    if repo:
        try:
            from cursor_sdk import CloudRepository
            cloud_kwargs["repos"] = [CloudRepository(url=repo, starting_ref="main")]
        except Exception:
            cloud_kwargs["repos"] = [{"url": repo, "starting_ref": "main"}]
    if _faenas_url():
        cloud_kwargs["env_vars"] = {"FAENAS_PUBLIC_URL": _faenas_url()}

    options = AgentOptions(
        api_key=key,
        model=modelo,
        cloud=CloudAgentOptions(**cloud_kwargs),
    )

    async def _run():
        async with await AsyncClient.launch_bridge(workspace=os.getcwd()) as client:
            return await AsyncAgent.prompt(mensaje, options, client=client)

    try:
        try:
            result = asyncio.run(_run())
        except RuntimeError as e:
            # Si ya hay un event loop (p.ej. worker async), crear uno nuevo en hilo.
            if "asyncio.run()" in str(e) or "running event loop" in str(e).lower():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    result = pool.submit(lambda: asyncio.run(_run())).result()
            else:
                raise
    except Exception as e:
        raise RuntimeError(_mensaje_error_cursor(str(e))) from e

    status = getattr(result, "status", None) or ""
    err_code = getattr(result, "error_code", None) or ""
    err_msg = getattr(result, "error_message", None) or ""
    texto = (getattr(result, "result", None) or getattr(result, "text", None) or "")
    if callable(texto):
        try:
            texto = texto()
        except Exception:
            texto = str(texto)
    texto = str(texto or "").strip()
    if str(status).lower() == "error" and not texto:
        detalle = (err_msg or err_code or "").strip()
        raise RuntimeError(
            _mensaje_error_cursor(
                detalle or f"Agente Cursor falló (run={getattr(result, 'id', '')})"
            )
        )
    parsed = _extraer_json_bloque(texto) or {}
    respuesta = (parsed.get("respuesta") or "").strip() or texto_sin_json(texto)
    propuestas = parsed.get("propuestas") if isinstance(parsed.get("propuestas"), list) else []
    return {
        "respuesta": respuesta or "Listo. Revisa las propuestas si las hay.",
        "propuestas": propuestas,
        "motor": "cursor",
        "modelo": modelo,
        "run_id": getattr(result, "id", "") or "",
    }


def _ejecutar_gestion(pregunta, contexto):
    # Preferir Cursor si hay CURSOR_API_KEY (keys del dashboard de Cursor).
    # Grok/xAI solo si la clave es de console.x.ai (suele empezar por xai-).
    if _cursor_key():
        return _ejecutar_agente_cursor(pregunta, contexto)
    gk = _grok_key()
    if gk and (gk.startswith("xai-") or gk.startswith("xai_")):
        return _ejecutar_agente_grok(pregunta, contexto)
    if gk:
        raise RuntimeError(
            "GROK_API_KEY no parece una key de xAI (debe ser xai-...). "
            "Si la creaste en Cursor, usa CURSOR_API_KEY."
        )
    raise RuntimeError("Configura CURSOR_API_KEY o GROK_API_KEY (xai-...) en el servidor")


def _worker_job(job_id, pregunta, faena_id, modo, historial):
    try:
        _actualizar_job(job_id, "running")
        contexto = _contexto_gestion(pregunta, faena_id=faena_id, modo=modo, historial=historial)
        out = _ejecutar_gestion(pregunta, contexto)
        _actualizar_job(job_id, "done", resultado=out)
    except Exception as e:
        _actualizar_job(job_id, "error", error=str(e))


def iniciar_job_gestion(pregunta, faena_id=None, modo="todo", historial=None):
    if not gestion_disponible():
        return {
            "ok": False,
            "error": "Jimmi gestión necesita GROK_API_KEY o CURSOR_API_KEY en el servidor (.env / Render)",
        }
    if _cursor_key():
        motor, modelo = "cursor", _cursor_model()
    else:
        motor, modelo = "grok", _grok_model()
    job_id = uuid.uuid4().hex[:16]
    _crear_job_db(job_id, pregunta, faena_id, modo)
    t = threading.Thread(
        target=_worker_job,
        args=(job_id, pregunta, faena_id, modo, historial or []),
        daemon=True,
    )
    t.start()
    return {
        "ok": True,
        "data": {
            "respuesta": f"Jimmi está gestionando con {motor}… Puedes seguir en la app; avisaré al terminar.",
            "propuestas": [],
            "ticket": None,
            "motor": f"{motor}_job",
            "modelo": modelo,
            "modo": modo,
            "pendiente": True,
            "job_id": job_id,
        },
    }
