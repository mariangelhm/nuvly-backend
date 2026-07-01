# Nuvly Backend MVP — Python 3.14.5

Backend MVP para el Studio de Nuvly.

## Inicio rápido

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
python -m uvicorn app.main:app --reload

Notas de autenticacion:
- No existe registro publico para trabajadores de Nuvly.
- La cuenta interna se asegura desde la base de datos/al iniciar el backend.
- Credenciales internas iniciales: `nuvlystudio@gmail.com` / `Admin.1234`
- Los usuarios internos tienen dos perfiles: `admin` y `developer`.
- Solo un `admin` puede crear usuarios internos desde `POST /api/admin/studio/users`.
```

cmd:

```cmd
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
python -m uvicorn app.main:app --reload

Notas de autenticacion:
- No existe registro publico para trabajadores de Nuvly.
- La cuenta interna se asegura desde la base de datos/al iniciar el backend.
- Credenciales internas iniciales: `nuvlystudio@gmail.com` / `Admin.1234`
```

Swagger:

```txt
http://127.0.0.1:8000/api/docs
```

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

# 1. Requisitos

Verifica tu versión en la terminal que uses.

PowerShell:

```powershell
python --version
```

cmd:

```cmd
python --version
```

Debe salir algo como:

```txt
Python 3.14.5
```

---

# 2. Crear entorno virtual

En la raíz del proyecto:

PowerShell:

```powershell
python -m venv .venv
```

cmd:

```cmd
python -m venv .venv
```

Activar en Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Activar en `cmd`:

```cmd
.venv\Scripts\activate.bat
```

Si PowerShell bloquea la activación:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Luego cierra y abre la terminal otra vez y ejecuta:

```powershell
.\.venv\Scripts\Activate.ps1
```

Cuando el entorno quede activo, verás algo como:

```txt
(.venv) C:\ruta\al\proyecto>
```

---

# 3. Actualizar herramientas de instalación

Esto es importante para Python 3.14.5.

PowerShell:

```powershell
python -m pip install --upgrade pip setuptools wheel
```

cmd:

```cmd
python -m pip install --upgrade pip setuptools wheel
```

---

# 4. Instalar dependencias

PowerShell:

```powershell
pip install -r requirements.txt
```

cmd:

```cmd
pip install -r requirements.txt
```

Si aparece error con `pydantic-core`, primero verifica que `requirements.txt` use versiones compatibles con Python 3.14.5, por ejemplo:

```txt
fastapi>=0.119.0
uvicorn[standard]>=0.37.0
pydantic>=2.12.0
pydantic-settings>=2.11.0
```

Luego limpia caché y reinstala.

PowerShell:

```powershell
pip cache purge
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

cmd:

```cmd
pip cache purge
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

Si quieres evitar depender de la activación del entorno virtual, también puedes usar el ejecutable directo del entorno.

PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

cmd:

```cmd
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Si el error menciona `link.exe not found`, te faltan compiladores de Windows y debes instalar `Visual Studio Build Tools` con la carga `Desktop development with C++`.

---

# 4.1. Levantar el backend localmente

Con el entorno ya activo:

PowerShell:

```powershell
python -m uvicorn app.main:app --reload

Notas de autenticacion:
- No existe registro publico para trabajadores de Nuvly.
- La cuenta interna se asegura desde la base de datos/al iniciar el backend.
- Credenciales internas iniciales: `nuvlystudio@gmail.com` / `Admin.1234`
```

cmd:

```cmd
python -m uvicorn app.main:app --reload

Notas de autenticacion:
- No existe registro publico para trabajadores de Nuvly.
- La cuenta interna se asegura desde la base de datos/al iniciar el backend.
- Credenciales internas iniciales: `nuvlystudio@gmail.com` / `Admin.1234`
```

Sin activar el entorno:

PowerShell:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

cmd:

```cmd
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Swagger quedará disponible en:

```txt
http://127.0.0.1:8000/api/docs
```

---

# 4.2. Deploy en Render

Render debe detectar `.python-version` en la raiz del repo con este contenido:

```txt
3.14.5
```

Start Command esperado:

```txt
python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

---

# 5. Crear MongoDB Atlas Free

Para desarrollo usaremos MongoDB Atlas Free, no Mongo local y no Docker.

Pasos:

1. Entra a MongoDB Atlas.
2. Crea un proyecto llamado `Nuvly`.
3. Crea un cluster gratuito.
4. Crea usuario y password.
5. Permite acceso desde tu IP.
6. En conexión selecciona `Conductores`.
7. Selecciona Python.
8. Copia el connection string.

Ejemplo:

```txt
mongodb+srv://nuvly_user:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
```

Reemplaza `<password>` por tu contraseña real.

---

# 6. Crear archivo `.env`

El archivo `.env.example` es solo una plantilla. Debes crear un archivo real llamado `.env` en la raíz del proyecto.

Contenido ejemplo:

```env
APP_NAME=Nuvly Backend
APP_ENV=development
API_PREFIX=/api

MONGODB_URI=mongodb+srv://TU_USUARIO:TU_PASSWORD@TU_CLUSTER.mongodb.net/?retryWrites=true&w=majority
MONGODB_DB_NAME=nuvly_dev

CORS_ORIGINS=http://localhost:5173,http://localhost:3000
PUBLIC_BASE_URL=http://localhost:8000
FRONTEND_PUBLIC_BASE_URL=http://localhost:5173
AUTH_SESSION_TTL_DAYS=30
```

`PUBLIC_BASE_URL` debe apuntar siempre al origen publico del backend.
Se usa para construir URLs absolutas de assets como `/static/uploads/...` en respuestas del API.

Ejemplos:

```env
# local
PUBLIC_BASE_URL=http://localhost:8000
FRONTEND_PUBLIC_BASE_URL=http://localhost:5173

# uat
PUBLIC_BASE_URL=https://api-uat.nuvlystudio.com
FRONTEND_PUBLIC_BASE_URL=https://uat.nuvlystudio.com
```

No subas `.env` a GitHub.

---

# 7. Levantar backend

Opción directa:

```powershell
python -m uvicorn app.main:app --reload

Notas de autenticacion:
- No existe registro publico para trabajadores de Nuvly.
- La cuenta interna se asegura desde la base de datos/al iniciar el backend.
- Credenciales internas iniciales: `nuvlystudio@gmail.com` / `Admin.1234`
```

O usando el script:

```powershell
.\run.ps1
```

La API quedará en:

```txt
http://localhost:8000
```

---

# 8. Abrir Swagger / OpenAPI

Swagger UI:

```txt
http://localhost:8000/api/docs
```

ReDoc:

```txt
http://localhost:8000/api/redoc
```

OpenAPI JSON:

```txt
http://localhost:8000/api/openapi.json
```

---

# 9. Probar health

Endpoint:

```http
GET /api/health
```

Respuesta esperada:

```json
{
  "status": "ok",
  "database": "ok",
  "service": "nuvly-backend"
}
```

Si falla aquí, normalmente es por:

- `MONGODB_URI` incorrecto
- password incorrecta
- IP no permitida en Atlas
- conexión a internet
- `.env` mal escrito

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

# Qué NO incluye todavía

- subida de imágenes
- presets reales desde base de datos
- preview privado por token
- historial de snapshots consultable
- duplicar experiencia
- soft delete
- formularios RSVP reales
- analytics
- Redis
- Docker obligatorio
- microservicios
- IA

Eso queda para versiones futuras.

---

# Problemas comunes

## Error: Failed building wheel for pydantic-core

Causa probable:

- pip viejo
- Pydantic viejo
- entorno virtual creado antes de actualizar dependencias

Solución:

```powershell
python -m pip install --upgrade pip setuptools wheel
pip install --upgrade "pydantic>=2.12.0" "fastapi>=0.119.0"
pip install -r requirements.txt
```

Si sigue fallando, borra `.venv` y créalo de nuevo:

```powershell
Remove-Item -Recurse -Force .venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

## Error conectando a MongoDB

Revisa:

- usuario
- password
- connection string
- IP permitida en MongoDB Atlas
- internet
- `.env`

## Swagger no abre

Verifica que el backend esté levantado:

```powershell
python -m uvicorn app.main:app --reload

Notas de autenticacion:
- No existe registro publico para trabajadores de Nuvly.
- La cuenta interna se asegura desde la base de datos/al iniciar el backend.
- Credenciales internas iniciales: `nuvlystudio@gmail.com` / `Admin.1234`
```

Luego abre:

```txt
http://localhost:8000/api/docs
```

## El frontend da error CORS

Agrega el puerto del frontend en:

```env
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

---

# Comandos rápidos

Crear entorno:

```powershell
python -m venv .venv
```

Activar entorno:

```powershell
.\.venv\Scripts\Activate.ps1
```

Actualizar herramientas:

```powershell
python -m pip install --upgrade pip setuptools wheel
```

Instalar dependencias:

```powershell
pip install -r requirements.txt
```

Levantar backend:

```powershell
python -m uvicorn app.main:app --reload

Notas de autenticacion:
- No existe registro publico para trabajadores de Nuvly.
- La cuenta interna se asegura desde la base de datos/al iniciar el backend.
- Credenciales internas iniciales: `nuvlystudio@gmail.com` / `Admin.1234`
```

Abrir Swagger:

```txt
http://localhost:8000/api/docs
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
