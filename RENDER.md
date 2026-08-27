# GitHub y Render — Faenas

Repo de trabajo (único): https://github.com/Ser3gix/faenas-app

No uses `faenas-backend`. Está vacío y no arranca nada.

## 1. Borrar el repo vacío en GitHub

El token de este entorno no puede borrar repositorios. En el navegador, con la cuenta `ser3gix@gmail.com`:

1. Abre https://github.com/Ser3gix/faenas-backend/settings
2. Al final, **Delete this repository**
3. Confirma el nombre `Ser3gix/faenas-backend`

Opcional: en https://github.com/Ser3gix/faenas-app/settings pasa el repo a **Private**.

## 2. Crear el servicio en Render

GitHub ya está conectado. En https://dashboard.render.com :

1. **New** → **Blueprint**
2. Elige **solo** `Ser3gix/faenas-app` (rama `main`)
3. Root Directory: déjalo vacío
4. Render leerá `render.yaml` (gunicorn + Python 3.12)

Si prefieres Web Service a mano:

- Runtime: Python
- Build: `pip install -r requirements.txt`
- Start: `gunicorn wsgi:app --bind 0.0.0.0:$PORT`

Si el log dice `No module named 'app'`, en Render → Settings → Start Command pon exactamente esa línea, o pulsa **Manual Deploy** tras subir `app.py`.

## 3. Variables de entorno (Environment)

Copia los valores desde tu `.env` local. No los subas a git.

Obligatorias (TiDB; el conector es el mismo que MySQL):

| Clave | Ejemplo |
|---|---|
| `DB_BACKEND` | `mysql` |
| `MYSQL_HOST` | host de TiDB Cloud |
| `MYSQL_PORT` | `4000` |
| `MYSQL_USER` | usuario TiDB |
| `MYSQL_PASSWORD` | contraseña |
| `MYSQL_DATABASE` | nombre de la base |
| `MYSQL_SSL` | `1` |

Fotos y PDF (Cloudflare R2):

| Clave | Ejemplo |
|---|---|
| `OBJECT_STORAGE_BACKEND` | `r2` |
| `OBJECT_STORAGE_BUCKET` | `faenas` |
| `OBJECT_STORAGE_ENDPOINT` | `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` |
| `OBJECT_STORAGE_PUBLIC_BASE_URL` | URL pública del bucket |
| `AWS_ACCESS_KEY_ID` | token R2 |
| `AWS_SECRET_ACCESS_KEY` | secreto R2 |

Opcionales:

| Clave | Uso |
|---|---|
| `PUBLIC_BASE_URL` | URL pública; si no, se usa `RENDER_EXTERNAL_URL` |
| `CLAVE_API` / `IA_API_KEY` | IA |
| `IA_MODO` | `local` o el modo cloud que uses |
| `IA_PROVIDER` | p. ej. `gemini` |
| `TICKET_CLAVE_API` | tickets |

El certificado `isrgrootx1.pem` va en el repo para SSL de MySQL.

## 4. Tras el primer deploy

- La web debe responder en `https://<servicio>.onrender.com`
- Móvil: `https://<servicio>.onrender.com/movil2`
- SQL en TiDB, fotos/PDF en Cloudflare R2.
- Planos y PolyBoard se quedan en el PC; al archivar se descarga un ZIP.
