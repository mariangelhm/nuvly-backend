# Contratos de edición y publicación

Los DTO/OpenAPI de `/api/docs` son la referencia de tipos. Preset es contenido inicial, config describe edición y renderer consume el proyecto. Una página tiene bloques identificados de forma estable; `pages` es autoritativo y `blocks` refleja la primaria. Los snapshots públicos son independientes de la revisión privada.

## Revisión de servidor

1. Leer el proyecto mediante la ruta customer del propietario o studio con sesión interna autorizada.
2. Mantener `updatedAt` devuelto como revisión de servidor.
3. Enviar `expectedUpdatedAt` en cada PUT del proyecto/template junto con los campos editables. Omisión: 428; conflicto: 409 `PROJECT_VERSION_CONFLICT`.
4. Conservar el borrador local ante 409. Leer el servidor y reconciliar explícitamente; no reintentar con una revisión inventada ni reemplazar cambios ajenos.

El repositorio compara id y revisión en una operación Mongo. La publicación protege el puntero de snapshot con la misma comparación. Un conflicto confirmado limpia el snapshot nuevo que no se adjuntó. Un error de transporte con resultado incierto no elimina automáticamente ese snapshot: el operador debe reconciliar punteros y snapshots antes de limpiar. No se promete una transacción multidocumento que no existe.

## Propiedad, precio y privacidad

`ownerId` autentica propiedad; un email coincidente no autoriza sobre otro owner. Recuperar legado sin owner requiere el endpoint claim y email verificado. Precio base, extras pagados y pago son del servidor. Un publish de cliente no acepta precio manual y requiere pago confirmado válido para el entorno.

Los GET privados conservan el contenido del editor. Las rutas públicas proyectan campos permitidos y eliminan contactos privados, huéspedes/respuestas, historial y secretos conocidos. El contenido editorial que el propio usuario escribe puede ser público; no existe un detector universal de secretos arbitrarios.

Invitaciones aceptan `content`, `templateComponent`, styles (fonts/themeTokens incluidos), layout y bloques; un DTO de escritura estricto rechaza campos desconocidos de nivel superior. El frontend usa `invitationWritePayload` para separar respuesta de escritura. Texto/listas vacíos y bloques desactivados deben sobrevivir guardar/recargar. Las webs distinguen `saveAsDraft=true` de la actualización/publicación explícita.

No existe `/api/invitations/temporary` en este backend. Los clientes comerciales crean desde template publicado y usan las rutas customer de lectura, actualización y publicación. El listado de productos entrega tarjetas, no documentos editables completos; ver [paginación](customer-product-pagination.md).

Validación operativa pendiente: CAS concurrente y reconciliación tras timeout en Mongo real, y comparación de preview/snapshot después del recorrido completo de edición en staging.

## Contrato de datos (fase 2)

Ver [modelo de datos](data-model-phase2.md): schemaVersion=1, importes CLP enteros, fechas ISO con zona en entradas estructurales, configuración JSON y validación de identidad/páginas/estados. expectedUpdatedAt se valida sin reformatear su texto. Antes del despliegue, ejecutar la auditoría de solo lectura para detectar registros históricos incompatibles.
