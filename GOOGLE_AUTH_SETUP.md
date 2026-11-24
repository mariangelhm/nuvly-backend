# Activar «Continuar con Google»

La integración usa Google Identity Services y las sesiones propias de Nuvly.
No necesita Firebase, Identity Platform, un secreto de cliente ni habilitar una
API de pago. El alojamiento y la base de datos conservan sus costos habituales.

## 1. Crear el ID público

1. Entra a [Google Auth Platform](https://console.cloud.google.com/auth/clients)
   y selecciona el proyecto de Google Cloud de Nuvly, o crea uno.
2. Completa **Branding** con el nombre Nuvly y tus correos de contacto.
3. En **Audience**, usa **External** para permitir cuentas de tus clientes.
   Si mantienes la aplicación en pruebas, agrega las cuentas de prueba que
   solicite Google. Para lanzarla, revisa y completa el estado de publicación.
4. En **Clients**, crea un cliente de tipo **Web application**.
5. Agrega estos **Authorized JavaScript origins** para desarrollo:

   ```text
   http://localhost
   http://localhost:5173
   ```

   Agrega también el origen HTTPS real de tu frontend al desplegarlo. No incluyas
   rutas como `/login` en los orígenes. Otro puerto de Vite necesita su propio origen.
6. Copia el **Client ID**, que termina en `.apps.googleusercontent.com`.
   Es público y puedes compartirlo para terminar la configuración.

Este flujo usa el botón oficial con callback JavaScript: no requiere configurar
una URL de redirección de OAuth. Solo pide la identidad básica (nombre y correo),
sin acceso a Gmail, Drive, contactos ni calendarios.

## 2. Configurar el backend

En `.env`, agrega el ID real:

```dotenv
GOOGLE_CLIENT_ID=TU_ID_REAL.apps.googleusercontent.com
```

Comprueba que `CORS_ORIGINS` incluya el origen exacto del frontend. Ejemplo local:

```dotenv
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

Instala las dependencias si es un entorno nuevo y reinicia el backend:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\run.ps1
```

El frontend obtiene el ID público del backend. No hay que duplicarlo en variables
`VITE_` ni poner un secreto en el navegador. Al iniciar, el backend crea el índice
único del identificador de Google y el índice de limpieza de los intentos de acceso.

## 3. Verificar con una cuenta real

1. Abre `http://localhost:5173/login` y pulsa **Continuar con Google**.
2. Elige una cuenta autorizada para tu aplicación y verifica que llegues a tu cuenta de Nuvly.
3. Repite desde un template del catálogo: debe continuar al editor del template elegido.
4. Comprueba cerrar sesión y entrar nuevamente.

Hasta tener el ID real y sus orígenes autorizados, la prueba completa con Google
queda pendiente. El acceso por correo y contraseña sigue disponible.

## Comportamiento de cuentas

- Google solo da acceso a cuentas de cliente; el acceso interno del equipo sigue separado.
- Una identidad de Google se reconoce por `sub`, no por el nombre o una foto.
- Un Gmail o correo de Workspace verificado puede vincularse a la cuenta de cliente
  con el mismo correo, conservando la contraseña que ya tuviera.
- Para otro correo ya registrado, se requiere ingresar con la contraseña existente;
  no se vincula automáticamente una cuenta cuya propiedad Google no puede garantizar.
- Se comprueban firma, emisor, destinatario, vencimiento y un nonce de un solo uso.
  El token de Google no se almacena en el navegador ni se pasa por la URL.
- Sin configuración válida, el botón informa que Google todavía no está disponible.

Referencia: [configuración oficial de Google Identity Services](https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid).
