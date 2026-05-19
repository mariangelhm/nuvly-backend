# Nuvly Backend MVP — Python 3.12

Backend MVP para el Studio de Nuvly.

Este servicio guarda, valida, publica y sirve experiencias visuales para:

- páginas web
- invitaciones digitales

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
Python 3.12.x
FastAPI moderno
Pydantic v2.12+
MongoDB Atlas
```

En Render necesitamos forzar Python 3.12 porque el servicio estaba tomando Python 3.14 por defecto y MongoDB Atlas fallaba con SSL handshake.

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

- Python 3.12.x
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
    modules/
      health/
        routes.py
      experiences/
        routes.py
        service.py
        repository.py
        schemas.py
        defaults.py
        normalizer.py
        registry.py
        utils.py
      published/
        routes.py
  requirements.txt
  .env.example
  run.ps1
  run.sh
  README.md
```

---

# 1. Requisitos

Verifica tu versión:

```powershell
python --version
```

Debe salir algo como:

```txt
Python 3.12.x
```

---

# 2. Crear entorno virtual

En la raíz del proyecto:

```powershell
python -m venv .venv
```

Activar en Windows PowerShell:

```powershell
.\.venv\Scripts\Activate
```

Si PowerShell bloquea la activación:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Luego activa de nuevo:

```powershell
.\.venv\Scripts\Activate.ps1
```

---

# 3. Actualizar herramientas de instalación

Esto es importante para Python 3.12:

```powershell
python -m pip install --upgrade pip setuptools wheel
```

---

# 4. Instalar dependencias

```powershell
pip install -r requirements.txt
```

Si aparece error con `pydantic-core`, ejecuta:

```powershell
python -m pip install --upgrade pip setuptools wheel
pip install --upgrade "pydantic>=2.12.0" "fastapi>=0.119.0"
pip install -r requirements.txt
```

---

# 4.1. Deploy en Render

Render debe detectar `.python-version` en la raiz del repo con este contenido:

```txt
3.12
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
```

No subas `.env` a GitHub.

---

# 7. Levantar backend

Opción directa:

```powershell
python -m uvicorn app.main:app --reload
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

```txt
experiences
```

---

## Snapshot publicado

Un snapshot es una copia congelada de la experiencia al momento de publicar.

Ejemplo:

1. El usuario publica una invitación rosada.
2. El backend crea un snapshot.
3. El usuario sigue editando el draft y cambia a azul.
4. La versión pública sigue rosada.
5. Solo cambia cuando vuelve a publicar.

Esto evita romper la versión pública con cambios a medias.

---

# Colecciones MongoDB

## `experiences`

Guarda la versión editable actual.

Campos principales:

```txt
id
title
slug
experienceType
status
presetId
styles
layout
blocks
seo
metadata
content
publishedSnapshotId
lastPublishedAt
createdAt
updatedAt
```

## `experience_snapshots`

Guarda versiones publicadas inmutables.

Campos principales:

```txt
id
experienceId
experienceType
slug
version
snapshot
createdAt
publishedAt
```

---

# Estados editoriales

```txt
draft
private_preview
published
archived
```

Reglas:

- `draft`: editable, no público.
- `private_preview`: futuro preview privado.
- `published`: visible públicamente desde snapshot.
- `archived`: no visible públicamente.

Cuando una experiencia está en `draft`, `private_preview` o `archived`, el backend fuerza `seo.noIndex = true`.

Cuando se publica, el backend fuerza `seo.noIndex = false`.

---

# Endpoints

## Health

```http
GET /api/health
```

## Crear experiencia

```http
POST /api/experiences
```

Body para web:

```json
{
  "experienceType": "web",
  "presetId": null,
  "title": "Nueva web"
}
```

Body para invitación:

```json
{
  "experienceType": "invitation",
  "presetId": null,
  "title": "Boda Mari y José"
}
```

## Listar experiencias

```http
GET /api/experiences?limit=20&skip=0
```

## Obtener experiencia editable

```http
GET /api/experiences/{experience_id}
```

## Guardar experiencia completa

```http
PUT /api/experiences/{experience_id}
```

Este MVP guarda el documento completo. No guarda parches pequeños todavía.

Body conceptual:

```json
{
  "title": "Buildframe Landing",
  "slug": "buildframe-landing",
  "experienceType": "web",
  "status": "draft",
  "presetId": null,
  "styles": {
    "themeId": "midnight",
    "colors": {
      "backgroundColor": "#07111d",
      "surfaceColor": "#0f1729",
      "textColor": "#eef5ff",
      "accentColor": "#5fe4ff"
    },
    "typography": {
      "headingFont": "Didot, serif",
      "subtitleFont": "Georgia, serif",
      "bodyFont": "Arial, sans-serif"
    }
  },
  "layout": {
    "sectionOrder": ["blk_nav", "blk_hero"]
  },
  "blocks": [
    {
      "id": "blk_nav",
      "type": "navigation",
      "variant": "N1-Overlay-Nav",
      "enabled": true,
      "order": 1,
      "props": {
        "title": "Buildframe",
        "buttonLabel": "Solicitar propuesta"
      },
      "settings": {
        "elementVisibility": {
          "buttonLabel": true
        }
      }
    },
    {
      "id": "blk_hero",
      "type": "hero",
      "variant": "H1-Centered",
      "enabled": true,
      "order": 2,
      "props": {
        "title": "Construimos espacios modernos",
        "subtitle": "Landing para constructora"
      },
      "settings": {}
    }
  ],
  "seo": {
    "title": "Buildframe Landing",
    "description": "Landing para constructora",
    "noIndex": true
  },
  "metadata": {
    "category": "landing",
    "style": "corporativo",
    "purpose": "captacion",
    "catalogVisible": false,
    "tags": []
  },
  "content": null
}
```

## Publicar experiencia

```http
POST /api/experiences/{experience_id}/publish
```

Hace esto:

1. obtiene la experiencia editable
2. valida estructura
3. normaliza bloques y layout
4. crea snapshot inmutable
5. marca la experiencia como `published`
6. guarda `publishedSnapshotId`
7. guarda `lastPublishedAt`
8. devuelve el snapshot creado

## Cambiar estado

```http
PATCH /api/experiences/{experience_id}/status
```

Body:

```json
{
  "status": "archived"
}
```

Si el estado enviado es `published`, internamente usa la lógica de publish.

## Obtener experiencia pública

```http
GET /api/published/{experienceType}/{slug}
```

Ejemplos:

```http
GET /api/published/web/buildframe-landing
```

```http
GET /api/published/invitation/boda-mari-y-jose
```

Este endpoint solo devuelve experiencias publicadas desde snapshot.

La vista pública del frontend debe consumir este endpoint, no el draft editable.

---

# Validaciones incluidas

El backend valida:

- `experienceType`: solo `web` o `invitation`
- `status`: solo `draft`, `private_preview`, `published`, `archived`
- `type` válido por bloque
- `variant` válida para ese `type`
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

## 1. Crear invitación

```http
POST /api/experiences
```

Body:

```json
{
  "experienceType": "invitation",
  "title": "Boda Mari y José",
  "presetId": null
}
```

Copia el `id` de la respuesta.

## 2. Obtener invitación

```http
GET /api/experiences/{id}
```

## 3. Publicar

```http
POST /api/experiences/{id}/publish
```

## 4. Ver público

El slug se genera desde el título. Para `Boda Mari y José`, el slug será:

```txt
boda-mari-y-jose
```

Endpoint:

```http
GET /api/published/invitation/boda-mari-y-jose
```

---

# Integración con frontend

El frontend debe consumir:

```txt
POST /api/experiences
GET /api/experiences/{id}
PUT /api/experiences/{id}
POST /api/experiences/{id}/publish
PATCH /api/experiences/{id}/status
GET /api/published/{experienceType}/{slug}
```

La vista editable usa:

```txt
GET /api/experiences/{id}
```

La vista pública usa:

```txt
GET /api/published/{experienceType}/{slug}
```

No usar el draft editable para render público.

---

# CORS

Por defecto:

```env
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

Si tu frontend corre en otro puerto, agrégalo.

---

# Logs

El backend imprime logs simples en consola:

```txt
Experience created
Experience updated
Experience published
MongoDB connected
```

No usamos herramientas caras de monitoreo todavía.

---

# Qué NO incluye todavía

- login
- usuarios
- ownerId / workspaceId
- subida de imágenes
- presets reales desde base de datos
- preview privado por token
- historial de snapshots consultable
- duplicar experiencia
- soft delete
- formularios RSVP reales
- analytics
- pagos
- emails
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
```

Abrir Swagger:

```txt
http://localhost:8000/api/docs
```
