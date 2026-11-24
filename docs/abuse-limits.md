# Límites antiabuso

La API limita solicitudes POST de autenticación, recuperación, creación de proyectos,
contacto y media por IP antes de procesar el cuerpo. Login y recuperación también
tienen presupuesto por cuenta/token; uploads y creación se limitan por usuario.
Los contadores de ventana fija viven en MongoDB, con incremento atómico e índice
TTL: se comparten entre workers e instancias. Los identificadores se almacenan
hasheados, sin emails, tokens ni IP en claro.

Respuestas: 429 al agotar presupuesto; el middleware IP devuelve Retry-After.
503 si el almacenamiento de contadores falla: no se permite abuso ilimitado como
fallback. Un fallo de contraseña también consume presupuesto. La ventana fija
permite ráfagas en su frontera; no pretende sustituir la protección del proveedor.

Media permite 20 solicitudes por minuto por usuario y, por defecto, 100 MiB de
upload al día (`MEDIA_OWNER_DAILY_UPLOAD_MB`). Los uploads fallidos pueden consumir
presupuesto. Este límite diario no equivale a una cuota total del volumen; se debe
monitorizar capacidad y retención en operación. Se mantienen límites por proyecto.

En staging se debe verificar el índice TTL, varias instancias, NAT legítimo y la
configuración de proxies de Uvicorn/edge. La IP proviene del scope ASGI; confiar
solo en proxies conocidos y no aceptar X-Forwarded-For arbitrario. Los tests locales
no ejecutan MongoDB real ni envían correos o archivos a infraestructura externa.
