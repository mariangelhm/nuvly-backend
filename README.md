# Nuvly Backend MVP — Python 3.14.5

Backend MVP para el Studio de Nuvly.

Para activar **Continuar con Google**, consulta [GOOGLE_AUTH_SETUP.md](GOOGLE_AUTH_SETUP.md).

## Verificación y operación

La instalación utiliza `requirements-lock.txt` y `requirements-dev-lock.txt` mediante los constraints de requirements. No copies un entorno virtual entre computadoras. Para instalar las herramientas de prueba:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade "pip>=26.3"
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -B scripts/test_offline.py
```

El runner usa fixtures y un directorio temporal, bloquea conexiones de red y no inicia el servidor contra Mongo real. Los locks se verificaron localmente en Python 3.14.5 Windows; el workflow prueba la instalación Linux cuando se ejecute en GitHub.

Guías operativas: [contratos y concurrencia](docs/api-contracts.md), [paginación](docs/customer-product-pagination.md), [uploads durables](docs/media-storage.md), [límites antiabuso](docs/abuse-limits.md) y [activación de Webpay](docs/production-payments.md). Las variables del entorno están en `.env.example`; los secretos se configuran fuera del repositorio.

Antes de promover una versión, verificar en staging TLS de Mongo, índices, restore de backups/assets, dos sesiones guardando el mismo borrador, aislamiento de clientes y retorno de pago. Conservar artefacto y configuración anteriores para rollback. Deshabilitar cobros nuevos antes de revertir un adaptador de pago; no eliminar pagos, snapshots ni uploads durante la reversión. Verificar compatibilidad de datos antes de revertir código que cambie esquemas. Los tests locales no habilitan producción automáticamente.

## Inicio rápido (entorno ya instalado)

Desde PowerShell, en la raíz del proyecto:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Abre http://127.0.0.1:8000/api/docs. Detén el servidor con `Ctrl+C`.
También puedes ejecutar `.\run.ps1`.

Para instalar desde cero o reparar un entorno copiado, sigue los pasos siguientes.

Este servicio guarda, valida, publica y sirve templates y proyectos visuales para:

- páginas web
- invitaciones digitales

Modelo actual del Studio:

- `pages[]` es la fuente principal de verdad para páginas editables.
- `blocks` en raíz sigue existiendo por compatibilidad y refleja los bloques de la página primaria.
- `metadata.linkedPages` se sigue exponiendo por compatibilidad y refleja las páginas `kind="linked"`.

Conceptos oficiales actuales:

- `type`: `website` | `invitation`
- `plan tier`: `essential` | `plus` | `pro` | `custom`
- `category`: por dominio de negocio, por ejemplo `construction`, `wedding`, `beauty`
- `variant level`: `core` | `advanced` | `premium`

La idea central es que el frontend **NO renderiza desde HTML guardado**. El frontend renderiza desde configuración estructurada:

- `styles`
- `layout`
- `blocks`
- `seo`
- `metadata`

---

## Decisión técnica de esta versión

Esta versión fue adaptada para trabajar con:

```txt
Python 3.14.5
FastAPI moderno
Pydantic v2.12+
MongoDB Atlas
```

En esta versión trabajamos directamente con Python 3.14.5.

Por eso el proyecto usa versiones modernas:

```txt
fastapi>=0.119.0
pydantic>=2.12.0
pydantic-settings>=2.11.0
pymongo>=4.15.0
uvicorn>=0.37.0
```

Antes de instalar dependencias, actualiza `pip`, `setuptools` y `wheel`.

---

## Stack

- Python 3.14.5
- FastAPI
- MongoDB Atlas Free
- PyMongo
- Pydantic v2
- Uvicorn

---

## Arquitectura

Por ahora este proyecto es un **monolito modular**:

- un solo backend
- una sola API
- una sola base de datos MongoDB
- módulos internos separados
- barato para desarrollo
- preparado para crecer

No usamos microservicios todavía.

---

## Estructura

```txt
nuvly-backend/
  app/
    main.py
    core/
      config.py
      database.py
      errors.py
      logging.py
      utils.py
    modules/
      domain/
        customer_routes.py
        public_routes.py
        studio_routes.py
        services.py
        repository.py
        schemas.py
      auth/
        routes.py
        service.py
        repository.py
        schemas.py
        dependencies.py
        email_service.py
      support/
        routes.py
        service.py
        schemas.py
        email_service.py
      health/
        routes.py
      payments/
        routes.py
      pricing/
        routes.py
  requirements.txt
  .env.example
  run.ps1
  run.sh
  README.md
```

---

# Instalación paso a paso en Windows (PowerShell)

## 1. Abrir la carpeta del proyecto

Abre una terminal PowerShell en la raíz, donde están `requirements.txt` y `app`.
En este equipo:

```powershell
Set-Location C:\Users\Mari\Documents\nuvly-backend-python314
```

## 2. Instalar Python 3.14.5

El proyecto usa la versión de `.python-version`: **3.14.5**.
El comando `python` del sistema puede seguir apuntando a otra versión.

En este equipo ya está instalado `uv`. Para instalar el Python requerido:

```powershell
uv python install 3.14.5
```

Si no tienes `uv`, instala Python 3.14.5 desde [Python.org](https://www.python.org/downloads/release/python-3145/)
y usa `py -3.14 -m venv .venv` en el siguiente paso, en lugar de `uv venv`.

## 3. Crear o reparar el entorno virtual

Solo para la primera instalación:

```powershell
uv venv --python 3.14.5 .venv
```

Si `.venv` ya funciona, omite su creación. Los entornos virtuales dependen del Python
y de las rutas del equipo donde se crearon: debes recrearlos si copiaste la carpeta.
Si aparece `did not find executable at 'D:\python\python.exe'`, detén el servidor,
abre una terminal nueva y conserva el entorno roto antes de crear otro:

```powershell
Rename-Item -Path .venv -NewName ('.venv-backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
uv venv --python 3.14.5 .venv
```

Comprueba la versión del entorno:

```powershell
.\.venv\Scripts\python.exe --version
```

Debe mostrar `Python 3.14.5`. En la reparación de este equipo, el respaldo quedó en
`.venv-backup-python314`. Los respaldos están excluidos de Git.

## 4. Instalar dependencias

Usa siempre el ejecutable del entorno para instalar y ejecutar:

```powershell
.\.venv\Scripts\python.exe -m ensurepip --upgrade
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

El último comando debe mostrar `No broken requirements found.`.

## 5. Configurar MongoDB y el archivo .env

Si `.env` ya existe, conserva su configuración. Si todavía no existe:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Abre `.env` y completa `MONGODB_URI` con la conexión real a MongoDB Atlas.
No uses los valores `USER`, `PASSWORD` ni `CLUSTER` de la plantilla.

En Atlas, crea el cluster y un usuario de base de datos, permite tu IP en el acceso
de red y copia la conexión para Python. Configura también:

```env
MONGODB_DB_NAME=nuvly_dev
PUBLIC_BASE_URL=http://localhost:8000
FRONTEND_PUBLIC_BASE_URL=http://localhost:5173
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

`PUBLIC_BASE_URL` es el origen público del backend y se usa para las URLs de assets.
`FRONTEND_PUBLIC_BASE_URL` es el origen del frontend. No subas `.env` a GitHub.

## 6. Iniciar el backend

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Mantén esa terminal abierta. Para detener el servidor, pulsa `Ctrl+C`.
También puedes usar `.\run.ps1`, que utiliza directamente el Python de `.venv`.

La activación del entorno es opcional. Si prefieres el comando corto, en cada
terminal nueva ejecuta primero:

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload
```

Si PowerShell bloquea `Activate.ps1` o `run.ps1`, usa el comando directo con
`.\.venv\Scripts\python.exe` del inicio de este paso.

En VS Code, selecciona `.venv\Scripts\python.exe` mediante **Python: Select Interpreter**.
Abre después una terminal nueva.

## 7. Verificar el servicio y MongoDB

- Swagger: http://127.0.0.1:8000/api/docs
- ReDoc: http://127.0.0.1:8000/api/redoc
- OpenAPI: http://127.0.0.1:8000/api/openapi.json

Desde otra terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

Espera `status: ready` y `database: ok`. Mientras termina la inicialización puede
responder HTTP 503 con `status: starting`; espera unos segundos y vuelve a consultar.
Si responde `database: error` o `status: degraded`, revisa la conexión de Atlas,
las credenciales, la IP permitida y el acceso a internet. Swagger puede abrir aunque
la conexión a MongoDB falle.

## Autenticación interna

- No existe registro público para trabajadores de Nuvly.
- El arranque no crea ni modifica usuarios internos. No hay credenciales iniciales predeterminadas.
- Los perfiles internos son `admin` y `developer`.
- Solo un `admin` puede crear usuarios internos desde `POST /api/admin/studio/users`.

Para provisionar el primer administrador, desde la raíz del backend y con el entorno
de destino configurado, un operador autorizado ejecuta:

```powershell
.\.venv\Scripts\python.exe -m scripts.create_internal_admin --email admin@example.com --name "Administrador"
```

El comando solicita y confirma la contraseña con entrada oculta, aplica la política
existente y solo inserta una cuenta nueva. Rechaza emails ya registrados, incluso
si pertenecen a un cliente o una cuenta interna desactivada. No acepta contraseñas
como argumentos, no imprime valores sensibles y no ejecuta el arranque del servidor,
siembra de precios ni creación de índices. El despliegue debe tener el índice único
de `users.emailNormalized` ya provisionado para impedir duplicados concurrentes.

En instalaciones anteriores, retirar el bootstrap no revoca credenciales ni sesiones
existentes. Antes de dar por cerrada la remediación operativa:

1. Desplegar esta corrección para impedir que un reinicio restaure la credencial anterior.
2. Rotar la contraseña de la cuenta afectada mediante un procedimiento administrativo
   autorizado, con contraseña generada y entregada por un canal seguro. La creación de
   otra cuenta no sustituye esta rotación; no convertir una cuenta cliente en interna.
3. Revocar todas las sesiones de esa identidad en `auth_sessions` y comprobar que sus
   tokens anteriores ya no autentican. Revocar también enlaces de recuperación pendientes.
4. Revisar accesos y copias de código, documentación, logs e historial que pudieran
   conservar la credencial anterior. Nunca copiar su valor a tickets o informes.

Estas operaciones se realizan explícitamente contra el entorno autorizado; no se
ejecutan al arrancar ni al instalar el código.

## Deploy en Render

Las imágenes de producción requieren un volumen durable configurado. Ver
[almacenamiento y restauración de media](docs/media-storage.md) antes de desplegar;
el backend rechaza una configuración productiva con uploads efímeros.

La versión de `.python-version` debe ser `3.14.5`.

Start Command:

```sh
python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

---

# Conceptos del backend

## Experience

Una experiencia puede ser:

```txt
web
invitation
```

Ambas usan el mismo motor:

```txt
styles + layout + blocks + seo + metadata + publicación
```

Por eso NO tendremos un backend distinto para webs y otro para invitaciones.

---

## Draft

Es la versión editable. Se guarda en la colección:

## Snapshot publicado

Un snapshot es una copia congelada del template o proyecto al momento de publicar.

Esto evita romper la versión pública con cambios a medias.

---

# Colecciones MongoDB

Colecciones activas del backend:

- `invitation_templates`
- `website_templates`
- `customer_invitations`
- `customer_websites`
- `invitation_template_snapshots`
- `website_template_snapshots`
- `customer_invitation_snapshots`
- `customer_website_snapshots`
- `payments`
- `pricing_plans`
- `pricing_components`

Las colecciones legacy `experiences` y `experience_snapshots` ya no forman parte de la API ni del modelo actual.

---

# Endpoints

## Health

```http
GET /api/health
```

## Studio

El backend actual expone endpoints separados para templates de invitación, templates de website y proyectos de cliente.

Revisa Swagger en `/api/docs` para el contrato vigente. Los endpoints legacy `/api/experiences/*` y `/api/published/{experienceType}/{slug}` fueron removidos.

## Auth

Autenticación Nuvly actualmente disponible:

- `POST /api/auth/register`
- `POST /api/auth/login` y `POST /api/admin/auth/login`
- `POST /api/admin/auth/login`
- `GET /api/auth/me`
- `POST /api/auth/logout`
- `POST /api/auth/forgot-password`
- `POST /api/auth/reset-password`
- `POST /api/support/contact`

Contrato base de sesión:

```json
{
  "token": "....",
  "tokenType": "bearer",
  "expiresAt": "2026-06-22T12:00:00+00:00",
  "authProvider": "nuvly",
  "authScope": "customer",
  "user": {
    "id": "usr_xxx",
    "name": "Lara",
    "email": "lara@test.dev",
    "accountType": "customer",
    "emailVerified": false,
    "active": true,
    "authProviders": ["nuvly"],
    "createdAt": "2026-06-22T12:00:00+00:00",
    "updatedAt": "2026-06-22T12:00:00+00:00",
    "lastLoginAt": "2026-06-22T12:00:00+00:00"
  }
}
```

Reglas de contraseña:

- mínimo 8 caracteres
- al menos una mayúscula
- al menos una minúscula
- al menos un número
- al menos un símbolo permitido
- símbolos permitidos solamente: `- / # $ % ! . ,`

Errores esperados en auth:

- `POST /api/auth/register`
- `422 AUTH_REGISTER_VALIDATION_ERROR` cuando faltan campos o no cumplen formato
- `409 EMAIL_ALREADY_REGISTERED` cuando el email ya existe
- `POST /api/auth/login`
- `422 AUTH_LOGIN_VALIDATION_ERROR` cuando faltan campos o no cumplen formato
- `401 INVALID_CREDENTIALS` cuando el email o la contraseña no coinciden
- `403 USER_INACTIVE` cuando la cuenta está desactivada
- los errores de validación incluyen `error.details` con objetos `{ field, message, type }`
- las sesiones de acceso expiran a los `30 días` por defecto (`AUTH_SESSION_TTL_DAYS`)
- el login de clientes usa `POST /api/auth/login`
- el login de desarrolladores y administradores usa `POST /api/admin/auth/login`

Soporte por correo:

- `POST /api/support/contact` envía un correo al soporte de Nuvly
- destino por defecto: `nuvlystudio@gmail.com`
- request:

```json
{
  "name": "Lara",
  "email": "lara@test.dev",
  "subject": "Necesito ayuda con mi cuenta",
  "message": "Hola, necesito ayuda para entrar al estudio."
}
```

- respuesta exitosa:

```json
{
  "ok": true,
  "message": "Tu mensaje fue enviado correctamente."
}
```

- errores esperados:
- `422 REQUEST_VALIDATION_ERROR` si faltan campos o tienen formato inválido
- `503 SUPPORT_EMAIL_UNAVAILABLE` si SMTP no está configurado
- `502 SUPPORT_EMAIL_SEND_FAILED` si falla el envío al proveedor SMTP

Recuperación de contraseña:

- desde catálogo, al presionar `Ver` o `Ver web`, el frontend debe abrir la pantalla de inicio de sesión
- la pantalla de cambio/restablecimiento de clave no se abre directamente desde catálogo
- desde la pantalla de inicio de sesión, la opción `Olvidé mi contraseña` debe abrir la pantalla de recuperación por email
- `POST /api/auth/forgot-password` recibe solo `email`
- responde éxito genérico aunque el email no exista
- si el email existe, envía un link a `${FRONTEND_PUBLIC_BASE_URL}/reset-password?token=...`
- el link de recuperación expira a los `10 minutos` por defecto (`AUTH_RESET_PASSWORD_TTL_MINUTES`)
- `POST /api/auth/reset-password` recibe `token`, `password`, `confirmPassword`

---

# Validaciones incluidas

El backend valida:

- `experienceType`: solo `web` o `invitation` en entidades vigentes
- estados editoriales de templates y proyectos de cliente
- estructura de `pages`, `blocks`, `layout`, `seo` y `metadata`
- bloques singleton no duplicados
- `order` normalizado
- `layout.sectionOrder` reconstruido desde bloques
- `slug` normalizado
- `seo.noIndex` según estado editorial

---

# Bloques soportados inicialmente

```txt
navigation
hero
story
details
gallery
countdown
map
rsvp
timeline
faq
footer
projects
services
proof
```

---

# Variantes soportadas inicialmente

```txt
navigation:
  N1-Overlay-Nav
  N2-Minimal-Nav

hero:
  H1-Centered
  H2-Split
  H3-Invitation-Cover

story:
  S1-Timeline
  S2-Centered-Text

details:
  D1-Cards
  D2-Minimal

gallery:
  G1-Grid
  G2-Carousel

countdown:
  C1-Classic
  C2-Minimal

map:
  M1-Google-Link
  M2-Card

rsvp:
  R1-Form
  R2-Compact

timeline:
  T1-Vertical
  T2-Horizontal

faq:
  F1-Accordion

footer:
  FO1-Minimal
  FO2-Brand

projects:
  P1-Grid
  P2-Showcase

services:
  SV1-Cards
  SV2-List

proof:
  PR1-Logos
  PR2-Testimonials
```

---

# Primer flujo de prueba en Swagger

Prueba el flujo vigente desde `/api/docs` con alguna de estas familias:

- `auth/register`
- `auth/login`
- `admin/auth/login`
- `auth/me`
- `auth/forgot-password`
- `auth/reset-password`
- `studio/invitation-templates`
- `studio/website-templates`
- `customers/invitations`
- `customers/websites`
- `public/invitation-templates`
- `public/website-templates`

---

# Integración con frontend

El frontend debe integrarse con los endpoints de `studio`, `customers` y `public` definidos en Swagger.

Los endpoints legacy de `experiences` y `published` ya no existen y no deben consumirse.

---

# CORS

Por defecto:

```env
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

Si tu frontend corre en otro puerto, agrégalo.

Si despliegas en UAT o producción, incluye también el dominio público del frontend y define `PUBLIC_BASE_URL` con el dominio público del backend.
Eso evita que las imágenes subidas dependan del host desde donde se esté abriendo el editor.

---

# Logs

El backend imprime logs simples en consola:

```txt
Customer project created
Customer project updated
Template published
MongoDB connected
```

No usamos herramientas caras de monitoreo todavía.

---

# Alcance operativo pendiente

Existen uploads autenticados, snapshots, reportes y eventos analíticos con consentimiento. Su operación requiere infraestructura y configuración del entorno. La habilitación real de cobros, restauración de volumen/backup, rotación de credenciales heredadas, pruebas con Mongo y observabilidad en producción no quedan certificadas por una instalación local. Mercado Pago sigue limitado a integración.

# Problemas comunes

## No module named uvicorn

Estás usando otro Python o faltan dependencias. Desde la raíz:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

## did not find executable / ruta de Python inexistente

El entorno virtual pertenece a otra instalación. Sigue el paso 3 para respaldarlo
y recrearlo, y luego reinstala las dependencias del paso 4.

## Failed building wheel for pydantic-core

Comprueba que `.\.venv\Scripts\python.exe --version` muestre `3.14.5` y actualiza
las herramientas del paso 4. Si el entorno era de otro equipo, recréalo.

## Error conectando a MongoDB

Revisa `.env`, las credenciales, el cluster y la IP permitida en Atlas. Consulta
`/api/health` como se indica en el paso 7 para distinguir el arranque HTTP de la
conexión a la base de datos.

## Swagger no abre

Mantén el servidor ejecutándose y abre http://127.0.0.1:8000/api/docs.
Si el puerto 8000 está ocupado, detén el servidor anterior o inicia en otro puerto:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8001
```

En ese caso, abre http://127.0.0.1:8001/api/docs.

## El frontend da error CORS

Incluye el origen y puerto del frontend en `CORS_ORIGINS` dentro de `.env` y
reinicia el backend. Ejemplo:

```env
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

---

# Contrato Studio Website Templates

## GET `/api/studio/website-templates/{id}`

Respuesta esperada para rehidratación del editor:

```json
{
  "id": "wtpl_xxx",
  "title": "Studio Contract Template",
  "slug": "studio-contract-template",
  "experienceType": "web",
  "status": "draft",
  "templateStatus": "draft",
  "styles": {
    "themeId": "solarized-studio",
    "colors": {},
    "typography": {}
  },
  "layout": {
    "sectionOrder": ["blk_navigation", "blk_hero"]
  },
  "pages": [
    {
      "id": "main",
      "kind": "primary",
      "title": "Web Principal",
      "slug": "",
      "path": "/",
      "parentPageId": null,
      "source": {
        "blockId": null,
        "blockType": null,
        "sourceItemIndex": null,
        "sourceChildKey": null
      },
      "seo": {},
      "settings": {},
      "blocks": [
        {
          "id": "blk_navigation",
          "type": "navigation",
          "label": "Navigation",
          "category": "marketing",
          "description": "Block navigation description",
          "variant": "navigation-variant-a",
          "enabled": true,
          "order": 1,
          "props": {},
          "settings": {}
        }
      ]
    },
    {
      "id": "navigation_services::nav-0::overview",
      "kind": "linked",
      "title": "Servicios overview",
      "slug": "servicios-overview",
      "path": "/servicios-overview",
      "parentPageId": "main",
      "source": {
        "blockId": "blk_navigation",
        "blockType": "navigation",
        "sourceItemIndex": 0,
        "sourceChildKey": "overview"
      },
      "seo": {},
      "settings": {
        "enabled": true,
        "tier": "pro"
      },
      "blocks": []
    }
  ],
  "blocks": [
    {
      "id": "blk_navigation",
      "type": "navigation",
      "label": "Navigation",
      "category": "marketing",
      "description": "Block navigation description",
      "variant": "navigation-variant-a",
      "enabled": true,
      "order": 1,
      "props": {},
      "settings": {}
    }
  ],
  "seo": {
    "title": "Studio Contract Template",
    "description": "Website template round-trip contract.",
    "noIndex": true
  },
  "metadata": {
    "category": "landing",
    "style": "editorial",
    "purpose": "lead-generation",
    "coverImage": "/assets/web-pages/image-1.png",
    "badge": "Nuevo",
    "featured": true,
    "level": "premium",
    "basePrice": 149,
    "tags": ["agency"],
    "catalogVisible": true,
    "previewVariant": "desktop",
    "previewStyle": {
      "frame": "browser"
    },
    "linkedPages": [
      {
        "id": "navigation_services::nav-0::overview",
        "kind": "linked",
        "title": "Servicios overview",
        "slug": "servicios-overview",
        "path": "/servicios-overview",
        "parentPageId": "main",
        "source": {
          "blockId": "blk_navigation",
          "blockType": "navigation",
          "sourceItemIndex": 0,
          "sourceChildKey": "overview"
        },
        "seo": {},
        "settings": {
          "enabled": true,
          "tier": "pro"
        },
        "blocks": []
      }
    ]
  },
  "statusHistory": [
    {
      "status": "draft",
      "changedAt": "2026-05-20T00:00:00Z",
      "changedBy": null,
      "reason": "initial_draft"
    }
  ],
  "publishedSnapshotId": null,
  "lastPublishedAt": null,
  "createdAt": "2026-05-20T00:00:00Z",
  "updatedAt": "2026-05-20T00:00:00Z"
}
```

Reglas del contrato:

- `experienceType` siempre debe salir como `"web"`.
- `pages[]` es el contrato canónico de páginas del editor.
- Debe existir exactamente una página `kind="primary"`.
- La página primaria debe usar `path="/"` y no puede tener `parentPageId`.
- Las páginas `kind="linked"` deben tener `parentPageId`, `path` absoluto y no pueden usar `path="/"`.
- `path`, `slug` e `id` deben ser únicos dentro del documento.
- `parentPageId` debe apuntar a una página existente.
- `styles`, `layout`, `blocks`, `seo` y `metadata` se devuelven completos, preservando claves extra persistidas por el front.
- `blocks` en raíz refleja siempre los bloques de la página primaria.
- `metadata.linkedPages` se mantiene por compatibilidad con clientes legacy y refleja las páginas `kind="linked"`.
- Cada bloque preserva `label`, `category`, `description`, `variant`, `props`, `settings` y cualquier otro campo adicional persistido.
- `websiteData` solo se devuelve si realmente fue persistido; el backend no inventa un objeto vacío.
- El contrato soporta round-trip `guardar -> leer -> guardar` sin perder información estructural del template.

Compatibilidad legacy:

- Si un cliente viejo envía solo `blocks` en raíz y/o `metadata.linkedPages`, el backend reconstruye `pages[]`.
- Si un cliente viejo hace `PUT` sin `pages`, el backend preserva las páginas existentes y no vacía la primaria.


## Calidad automática

Instala las dependencias de desarrollo de `requirements-dev.txt` y ejecuta `python scripts/check_quality.py --tests` desde el entorno Python 3.14.5 del proyecto. Incluye lint/formato de app/scripts/tests, tipos estrictos en ocho módulos de contratos y pruebas offline. [Alcance, comandos y CI](docs/quality-phase4.md).


## Validación operativa (fase 5)

`python scripts/validate_staging.py --output <reporte.json>` recoge evidencia de solo lectura; `--env-file` selecciona configuración de staging. La auditoría agregada se ejecuta con `python scripts/audit_data_contracts.py --summary`. El ensayo con escrituras requiere un destino nuevo aislado explícito y conserva fixtures para revisión. [Estado, alcance y requisitos de cierre](docs/operations-phase5.md).
