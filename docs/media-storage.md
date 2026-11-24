# Almacenamiento de imágenes

Los uploads aceptan JPG/PNG/WebP autenticados, con límites de cuerpo, archivo y
dimensiones. Nuevos SVG se rechazan; los SVG antiguos servidos por la API llevan
CSP sandbox. Las URLs públicas mantienen `/static/uploads/{scope}/{filename}`.

Desarrollo conserva `static/uploads`. Producción requiere un volumen persistente
montado y estas variables, administradas en el entorno de despliegue:

```dotenv
MEDIA_STORAGE_ROOT=/var/data/nuvly-media
MEDIA_STORAGE_DURABLE=true
```

El flag declara una garantía del operador, no crea un disco ni demuestra que sea
durable. La aplicación rechaza arrancar en producción sin ruta absoluta y esta
declaración. El volumen debe estar respaldado y accesible a la instancia; varias
instancias requieren almacenamiento compartido, no discos locales independientes.

Migración autorizada: detener escrituras, respaldar uploads y metadata, copiar el
contenido de `static/uploads` al volumen manteniendo rutas/filenames, comparar
conteos y SHA-256, configurar el montaje y verificar URLs antiguas antes de reabrir
escrituras. No se modifican URLs ni documentos por cambiar la ubicación física.
Conservar el respaldo para rollback; no borrar el origen durante la validación.

Antes de lanzar: subir una imagen ficticia, reiniciar/reemplazar la instancia y
confirmar la misma URL y checksum; restaurar una copia en staging aislado y comprobar
assets y metadata. Registrar fecha, responsable, ubicación del backup, RPO/RTO
medidos y evidencia. Estas pruebas reales de infraestructura están pendientes;
las pruebas unitarias solo simulan dos directorios de aplicación y el mismo volumen.
