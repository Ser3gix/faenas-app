# object_storage.py — Cloudflare R2 (API compatible con S3)

import re
from urllib.parse import urlparse

_cliente = None
_error_cliente = ""


def _limpiar_valor(texto):
    t = (texto or "").replace("\r", "").replace("\n", "").replace("\t", "")
    t = t.replace("\u00a0", " ").strip()
    return t.strip("\"'").strip()


def normalizar_endpoint_r2(endpoint):
    """Acepta ID de cuenta, host sin https o URL con ruta; devuelve solo el host S3."""
    t = _limpiar_valor(endpoint)
    if not t:
        return "", "Falta el endpoint"
    bajo = t.lower()
    if "r2.dev" in bajo:
        return "", "Eso es la URL pública (r2.dev). El endpoint es https://<ID-de-cuenta>.r2.cloudflarestorage.com (R2 → Ajustes de API S3)."
    solo = t.replace("https://", "").replace("http://", "").strip("/")
    if re.fullmatch(r"[0-9a-fA-F]{32}", solo):
        t = f"https://{solo.lower()}.r2.cloudflarestorage.com"
    if t.startswith("http://"):
        t = "https://" + t[7:]
    if not t.lower().startswith("https://"):
        t = "https://" + t.lstrip("/")
    partes = urlparse(t)
    host = (partes.netloc or "").split("@")[-1]
    if not host:
        return "", "Endpoint no válido"
    if "r2.cloudflarestorage.com" not in host.lower() and "amazonaws.com" not in host.lower():
        if "." not in host and re.fullmatch(r"[0-9a-fA-F]{32}", host):
            host = f"{host.lower()}.r2.cloudflarestorage.com"
        else:
            return "", "El endpoint debe ser https://<ID-de-cuenta>.r2.cloudflarestorage.com (no la URL pública)."
    return f"https://{host}", ""


def traducir_error_r2(exc):
    msg = str(exc or "")
    bajo = msg.lower()
    if "certificate" in bajo or "ssl" in bajo or "certificateverify" in bajo:
        return "Python no valida el certificado SSL. En el PC: pip install -U certifi boto3"
    if "invalidaccesskeyid" in bajo or "invalidaccesskey" in bajo:
        return "Access key incorrecta. En Cloudflare: R2 → Administrar tokens de API R2."
    if "signaturedoesnotmatch" in bajo:
        return "Secret key incorrecta, o copiada con un espacio de más."
    if "nosuchbucket" in bajo:
        return "El bucket no existe o el nombre no coincide (mayúsculas y minúsculas cuentan)."
    if "accessdenied" in bajo or "403" in bajo:
        return "El token no tiene permiso sobre ese bucket. Crea un token R2 con lectura y escritura de objetos en ese bucket."
    if "getaddrinfo" in bajo or "nameresolution" in bajo or "failed to establish" in bajo or "newconnectionerror" in bajo:
        return "No se alcanza el endpoint. Debe ser https://<ID-de-cuenta>.r2.cloudflarestorage.com"
    if "timed out" in bajo or "timeout" in bajo:
        return "Cloudflare no responde. Revisa internet o el firewall."
    return msg[:280]


def _codigo_s3(exc):
    try:
        return str((exc.response or {}).get("Error", {}).get("Code") or "")
    except Exception:
        return ""


def r2_activo():
    from config import (
        OBJECT_STORAGE_ACCESS_KEY,
        OBJECT_STORAGE_BACKEND,
        OBJECT_STORAGE_BUCKET,
        OBJECT_STORAGE_ENDPOINT,
        OBJECT_STORAGE_SECRET_KEY,
    )
    backend = (OBJECT_STORAGE_BACKEND or "").strip().lower()
    return (
        backend in {"r2", "s3", "cloudflare"}
        and bool(OBJECT_STORAGE_BUCKET)
        and bool(OBJECT_STORAGE_ENDPOINT)
        and bool(OBJECT_STORAGE_ACCESS_KEY)
        and bool(OBJECT_STORAGE_SECRET_KEY)
    )


def r2_listo():
    return _get_cliente() is not None


def r2_error():
    if r2_listo():
        return ""
    if not r2_activo():
        return "Faltan datos de Cloudflare R2 en el PC (.env)"
    return _error_cliente or "No se pudo conectar a Cloudflare R2"


def reiniciar_cliente():
    global _cliente, _error_cliente
    _cliente = None
    _error_cliente = ""


def probar_conexion():
    """Comprueba el acceso al bucket. No exige permiso de listado."""
    cliente = _get_cliente()
    if not cliente:
        return False, r2_error()
    from config import OBJECT_STORAGE_BUCKET
    try:
        cliente.head_bucket(Bucket=OBJECT_STORAGE_BUCKET)
        return True, ""
    except Exception as exc:
        codigo = _codigo_s3(exc)
        if codigo in {"404", "NoSuchBucket", "NotFound"}:
            return False, traducir_error_r2(exc)
        try:
            cliente.get_object(Bucket=OBJECT_STORAGE_BUCKET, Key="__faenas_conexion__")
            return True, ""
        except Exception as exc2:
            codigo2 = _codigo_s3(exc2)
            texto = str(exc2)
            if codigo2 == "NoSuchKey" or "nosuchkey" in texto.lower():
                return True, ""
            if codigo2 in {"404", "NotFound"} and "nosuchbucket" not in texto.lower():
                return True, ""
            if codigo2 in {"InvalidAccessKeyId", "SignatureDoesNotMatch", "AccessDenied", "InvalidAccessKey"}:
                return False, traducir_error_r2(exc2)
            return False, traducir_error_r2(exc2 if codigo2 else exc)


def _get_cliente():
    global _cliente, _error_cliente
    if _cliente is not None:
        return _cliente
    if not r2_activo():
        return None
    try:
        import boto3
        from botocore.config import Config as BotoConfig
    except Exception as exc:
        _error_cliente = "Falta el paquete boto3 en el servidor"
        print(f"✗ Cloudflare R2: {_error_cliente} ({exc})")
        return None
    kwargs = dict(
        signature_version="s3v4",
        s3={"addressing_style": "path"},
    )
    try:
        boto_config = BotoConfig(
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
            **kwargs,
        )
    except TypeError:
        boto_config = BotoConfig(**kwargs)
    try:
        from config import (
            OBJECT_STORAGE_ACCESS_KEY,
            OBJECT_STORAGE_ENDPOINT,
            OBJECT_STORAGE_REGION,
            OBJECT_STORAGE_SECRET_KEY,
        )
        extra = {}
        try:
            import certifi
            extra["verify"] = certifi.where()
        except Exception:
            pass
        _cliente = boto3.client(
            "s3",
            endpoint_url=OBJECT_STORAGE_ENDPOINT,
            aws_access_key_id=OBJECT_STORAGE_ACCESS_KEY,
            aws_secret_access_key=OBJECT_STORAGE_SECRET_KEY,
            region_name=OBJECT_STORAGE_REGION or "auto",
            config=boto_config,
            **extra,
        )
        _error_cliente = ""
        return _cliente
    except Exception as exc:
        _error_cliente = str(exc)
        print(f"✗ Cloudflare R2: {exc}")
        return None


def clave_objeto(*partes):
    limpio = []
    for parte in partes:
        texto = str(parte or "").replace("\\", "/").strip("/")
        texto = texto.replace("..", "")
        if texto:
            limpio.append(texto)
    return "/".join(limpio)


def url_publica(object_key):
    if not object_key:
        return ""
    from config import OBJECT_STORAGE_BUCKET, OBJECT_STORAGE_PUBLIC_BASE_URL
    base = (OBJECT_STORAGE_PUBLIC_BASE_URL or "").rstrip("/")
    if base:
        return f"{base}/{object_key.lstrip('/')}"
    cliente = _get_cliente()
    if not cliente:
        return ""
    try:
        return cliente.generate_presigned_url(
            "get_object",
            Params={"Bucket": OBJECT_STORAGE_BUCKET, "Key": object_key},
            ExpiresIn=60 * 60 * 24 * 7,
        )
    except Exception:
        return ""


def subir_bytes(object_key, data, content_type="application/octet-stream"):
    from config import OBJECT_STORAGE_BUCKET
    cliente = _get_cliente()
    if not cliente:
        return {"ok": False, "error": r2_error() or "Cloudflare R2 no está configurado"}
    cliente.put_object(
        Bucket=OBJECT_STORAGE_BUCKET,
        Key=object_key,
        Body=data,
        ContentType=content_type or "application/octet-stream",
    )
    return {
        "ok": True,
        "key": object_key,
        "bucket": OBJECT_STORAGE_BUCKET,
        "url": url_publica(object_key),
    }


def borrar_objeto(object_key):
    if not object_key:
        return True
    from config import OBJECT_STORAGE_BUCKET
    cliente = _get_cliente()
    if not cliente:
        return False
    try:
        cliente.delete_object(Bucket=OBJECT_STORAGE_BUCKET, Key=object_key)
        return True
    except Exception:
        return False


def descargar_bytes(object_key):
    cliente = _get_cliente()
    if not cliente or not object_key:
        return None
    from config import OBJECT_STORAGE_BUCKET
    try:
        resp = cliente.get_object(Bucket=OBJECT_STORAGE_BUCKET, Key=object_key)
        return resp["Body"].read()
    except Exception:
        return None
