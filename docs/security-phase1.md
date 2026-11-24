# Plan de mejora y fase 1: seguridad e integridad

Fecha: 2026-11-24. Implementación local; sin despliegue ni migración de la base real.

## Seguimiento de las cinco fases

1. Seguridad e integridad: cambios implementados y verificados con fixtures locales. Validación del entorno pendiente en fase 5.
2. Modelo de datos: implementado y verificado localmente; ver [fase 2](data-model-phase2.md). Auditoría de datos reales pendiente en fase 5.
3. Mantenibilidad y legibilidad: refactorización implementada y verificada localmente; ver [fase 3](maintainability-phase3.md).
4. Calidad automática: controles y workflows implementados y verificados localmente; ver [fase 4](quality-phase4.md). Tipos y formato frontend tienen alcance incremental explícito.
5. Validación operativa: en curso; TLS de Mongo y auditoría de lectura realizados en desarrollo. Cierre pendiente de staging/accesos y ensayos reales; ver [fase 5](operations-phase5.md).

## Cambios de fase 1

- El frontend solicita sesiones mediante cookies HttpOnly. El backend no incluye el token en el JSON de ese modo. LocalStorage conserva metadatos de interfaz, nunca el token de estas sesiones. El arranque del frontend elimina credenciales bearer heredadas y exige iniciar sesión nuevamente.
- Cookies independientes para customer/internal, host-only, limitadas al prefijo API. Fuera de development/test usan Secure y SameSite=None; en desarrollo usan SameSite=Lax sin Secure para HTTP local. Configurar APP_ENV=production en producción.
- Las peticiones con cookie requieren X-Nuvly-Session-Mode: cookie y X-Nuvly-Auth-Scope. Las escrituras exigen Origin explícito incluido exactamente en CORS_ORIGINS. Las lecturas con Origin también lo validan; sin Origin solo se aceptan con cabeceras personalizadas. Un formulario o navegación con cookies solas no autentica. No se habilita wildcard CORS.
- El cliente envía credenciales solo al origen y prefijo de API configurados; los GET concurrentes separan scope y sesión. El frontend exige soporte de cookies del backend, sin fallback silencioso a tokens persistidos.
- Los clientes API con Authorization: Bearer siguen disponibles. Los permisos provienen del usuario y sesión en servidor. El scope guardado en la sesión debe coincidir con el tipo de cuenta actual.
- Ambos logout revocan el token en servidor y eliminan su cookie. Cambiar contraseña rota credentialsVersion; las sesiones previas dejan de autenticar. Los registros antiguos sin versión siguen funcionando hasta una rotación. El login con contraseña verifica esa versión al registrar el acceso, y el login de Google actualiza solo sus propios campos para no restaurar credenciales antiguas ante un reset concurrente. Otros enlaces de recuperación anteriores también dejan de servir; la escritura de credenciales usa CAS sobre credentialsVersion para evitar que dos enlaces concurrentes reemplacen una contraseña recién cambiada. La reclamación del token de recuperación usa update_one condicionado a usedAt=null, antes de modificar la contraseña. Si la escritura posterior falla hay que solicitar otro enlace; no se declara transacción multidocumento.
- Hashes de contraseña malformados fallan cerrados. Se preserva el algoritmo existente; no se rehashean usuarios ni se cambian credenciales reales.
- Health público devuelve 503 si el arranque no terminó correctamente o Mongo falla, sin exponer excepciones. Los errores quedan en el sistema de logs con su redacción existente.
- Respuestas privadas: Cache-Control: no-store. Cabeceras nosniff y no-referrer. Se amplían límites por IP a preview/creación de checkout, webhook de Mercado Pago y reenvío de recibos.
- El arranque ya no elimina índices. Incompatibilidades de índices degradan readiness; los reemplazos se ejecutan explícitamente mediante scripts/migrate_security_indexes.py, que conserva definiciones ya correctas.
- Configuración: CORS acepta orígenes explícitos sin rutas, usuarios ni wildcards. En producción se requieren URLs HTTPS explícitas de frontend/backend y el frontend debe figurar en CORS.

## Despliegue coordinado

1. Respaldar Mongo y verificar restauración. En una ventana sin escrituras, ejecutar desde el backend `python scripts/migrate_security_indexes.py` con la configuración del entorno. El script elimina solo los índices legacy conocidos que requieren reemplazo; si Mongo informa duplicados hay que resolverlos antes de continuar. No se ejecutó contra una base real en esta fase.
2. Configurar APP_ENV=production, PUBLIC_BASE_URL, FRONTEND_PUBLIC_BASE_URL y CORS_ORIGINS como orígenes HTTPS explícitos; servir API y frontend con TLS. Desplegar primero el backend, compatible con bearer, y después el frontend.
3. Usar frontend/API bajo el mismo sitio, por ejemplo app.ejemplo.cl y api.ejemplo.cl, o un proxy del mismo origen. Aunque SameSite=None admite requests cross-site, navegadores que bloquean cookies de terceros pueden impedir esas sesiones. No volver a guardar tokens como alternativa.
4. Tras el cambio, los usuarios con tokens antiguos en el navegador vuelven a iniciar sesión. Sus proyectos no se modifican. Probar login cliente/equipo, refresh, carga de imágenes, edición, checkout, logout y recuperación de contraseña.
5. No revertir al frontend que persiste bearer como rollback de seguridad. Conservar backend y frontend compatibles con cookies; los permisos de CORS deben permanecer limitados al entorno.

## Evidencia y límites

Las pruebas offline cubren login-cookie/me/logout mediante las rutas ASGI reales, orígenes no confiables, separación de cookies, compatibilidad bearer, invalidación tras reset, reclamación exclusiva del token, hashes inválidos, readiness público, configuración CORS/HTTPS, creación no destructiva de índices y repetibilidad de migración con dobles.

Frontend: pruebas unitarias/regresiones y build, incluyendo metadatos sin token, limpieza del almacenamiento heredado, alcance de credenciales y separación de requests por scope.

No equivalen a validación de infraestructura: falta probar cookies en navegadores reales con los dominios finales, proxy/IP confiable para rate limits, atomicidad/índices en Mongo real y recorridos de pagos/almacenamiento. Estas comprobaciones corresponden a fase 5. Las cookies HttpOnly reducen extracción de credenciales por JavaScript; prevenir XSS sigue siendo necesario porque un script ejecutado en el origen puede realizar acciones autenticadas. No se declara una auditoría exhaustiva ni seguridad absoluta.

Verificación final local: backend 418 pruebas; frontend 132 casos unitarios y 99 regresiones; build de producción aprobado. Las advertencias de deprecación de HTTP 422 existentes quedan para la fase de calidad.
