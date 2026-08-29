from database import inicializar_db
from server2 import app
from object_storage import r2_listo, r2_error

inicializar_db()
if r2_listo():
    print("✓ Cloudflare R2 listo")
else:
    print(f"✗ Cloudflare R2: {r2_error()}")
