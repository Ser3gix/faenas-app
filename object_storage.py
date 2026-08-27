# object_storage.py — Cloudflare R2 (API compatible con S3)
from config import (
    OBJECT_STORAGE_ACCESS_KEY,
    OBJECT_STORAGE_BACKEND,
    OBJECT_STORAGE_BUCKET,
    OBJECT_STORAGE_ENDPOINT,
    OBJECT_STORAGE_PUBLIC_BASE_URL,
    OBJECT_STORAGE_REGION,
    OBJECT_STORAGE_SECRET_KEY,
)

_cliente = None


def r2_activo():
    backend = (OBJECT_STORAGE_BACKEND or "").strip().lower()
    return (
        backend in {"r2", "s3", "cloudflare"}
        and bool(OBJECT_STORAGE_BUCKET)
        and bool(OBJECT_STORAGE_ENDPOINT)
        and bool(OBJECT_STORAGE_ACCESS_KEY)
        and bool(OBJECT_STORAGE_SECRET_KEY)
    )


def _get_cliente():
    global _cliente
    if _cliente is not None:
        return _cliente
    if not r2_activo():
        return None
    try:
        import boto3
        from botocore.config import Config as BotoConfig
    except Exception:
        return None
    _cliente = boto3.client(
        "s3",
        endpoint_url=OBJECT_STORAGE_ENDPOINT,
        aws_access_key_id=OBJECT_STORAGE_ACCESS_KEY,
        aws_secret_access_key=OBJECT_STORAGE_SECRET_KEY,
        region_name=OBJECT_STORAGE_REGION or "auto",
        config=BotoConfig(signature_version="s3v4"),
    )
    return _cliente


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
    cliente = _get_cliente()
    if not cliente:
        return {"ok": False, "error": "Cloudflare R2 no está configurado"}
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
    try:
        resp = cliente.get_object(Bucket=OBJECT_STORAGE_BUCKET, Key=object_key)
        return resp["Body"].read()
    except Exception:
        return None
