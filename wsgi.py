from database import inicializar_db
from server2 import app
from object_storage import probar_conexion, r2_activo, r2_error

inicializar_db()
if r2_activo():
    ok, err = probar_conexion()
    if ok:
        print("✓ Cloudflare R2 conectado")
    else:
        print(f"✗ Cloudflare R2: {err}")
else:
    print(f"✗ Cloudflare R2: {r2_error()}")
