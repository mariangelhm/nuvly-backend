# Fase 5: validación operativa

Fecha: 2026-11-24. **En curso; no certificada ni cerrada.** El entorno disponible declara development y usa nuvly_dev. La URL remota encontrada en el frontend está marcada como producción; no se identificó un staging confirmado.

## Evidencia obtenida

| Comprobación | Resultado observado |
| --- | --- |
| Mongo real, configuración local | Conexión y ping con TLS, certificados y hostname verificados: aprobado. |
| Auditoría de contratos de datos | 89 documentos revisados, 0 problemas detectados por las reglas del auditor. |
| Índice de paginación customer_websites | No se encontró el compuesto ownerId asc / updatedAt desc / id asc. No se creó ni modificó ningún índice. |
| API y frontend configurados localmente | No respondieron; los intentos terminaron con ConnectionError. |
| Identidad de staging | Pendiente de confirmar; APP_ENV=development. |
| HTTPS y cookies de staging | Las URLs configuradas son HTTP local; no validan el comportamiento Secure/SameSite de un despliegue HTTPS. |
| Almacenamiento durable | No está declarado en esta configuración. El reinicio/reemplazo y la restauración siguen pendientes. |
| Configuración de pagos | Integración configurada y producción deshabilitada; esto no equivale a probar el formulario bancario. |

Los reportes sin credenciales ni contenido de clientes están en [preflight local](qa/phase5-local-preflight.json) y [auditoría agregada](qa/phase5-data-audit.json). La auditoría revisó 4 templates web, 42 webs de cliente, 8 planes, 29 componentes, 5 pagos y 1 descuento. No se modificaron datos de Mongo, cuentas, pagos, imágenes ni despliegues.

La auditoría cubre las reglas definidas en scripts/audit_data_contracts.py; no es una validación universal de todos los datos, un backup consistente ni una prueba del recorrido de edición en la API.

## Herramientas preparadas y verificadas

### Preflight de solo lectura

Desde el backend:

```powershell
.\.venv\Scripts\python.exe scripts/validate_staging.py --output docs/qa/phase5-local-preflight.json
```

Lee por defecto la configuración del archivo .env del backend, independientemente del directorio de invocación. Las variables de entorno siguen teniendo precedencia. `--env-file <ruta>` permite elegir un archivo de staging sin modificar .env.

El preflight comprueba configuración, conexión TLS a Mongo, índice de listado y respuestas HTTP. No crea índices ni arranca servicios. Los mensajes internos, URIs y cuerpos de error HTTP no se guardan. phaseComplete permanece false: un ping y un flag de configuración no certifican toda esta fase. Una declaración MEDIA_STORAGE_DURABLE=true también requiere evidencia real de reinicio y restauración.

### Ensayo de Mongo con base nueva aislada

Preparado, **todavía no ejecutado contra Mongo real**, pendiente de confirmar el entorno y autorizar el destino de las fixtures:

```powershell
.\.venv\Scripts\python.exe scripts/validate_staging.py --env-file .env.staging --exercise-database nuvly_validation_20261124_run01 --output docs/qa/phase5-mongo-isolated.json
```

`.env.staging` es un ejemplo de destino pendiente de configurar, no un archivo existente ni un entorno ya validado.

El modo de ensayo exige ambiente development/test/staging/uat, pagos de integración sin producción y una base nueva con prefijo nuvly_validation_. Rechaza la base configurada de la aplicación y cualquier destino ya existente. Reserva una colección de control y no elimina bases ni fixtures automáticamente.

El ensayo crea 300 proyectos sintéticos de dos propietarios y sus índices en la base nueva. Ejecuta el pipeline real de paginación, comprueba orden/conteo/aislamiento/proyección, consulta explain con executionStats y exige el índice compuesto en el plan ganador. Después ejecuta ocho escrituras CAS simultáneas mediante DomainRepository: debe guardar exactamente una y devolver siete conflictos. Verifica también la lectura posterior a la escritura.

El resultado mide estas operaciones en Mongo real; no simula un timeout de red real, no prueba un snapshot publicado, no demuestra rendimiento a escala y no valida infraestructura de backups. Las fixtures se conservan para revisión; su eliminación queda como acción separada del operador.

### Auditoría agregada de datos existentes

```powershell
.\.venv\Scripts\python.exe scripts/audit_data_contracts.py --summary
```

Solo imprime conteos por colección y códigos de incidencias. El modo histórico sin --summary sigue disponible para ubicar problemas por identificador, sin imprimir contenido editorial ni datos de contacto.

## Condiciones para cerrar la fase

1. Confirmar URLs de API/frontend, configuración y cuenta(s) de prueba del entorno elegido, más la versión de código desplegada. Las declaraciones APP_ENV y el nombre de la base no demuestran por sí solos que un cluster sea staging.
2. Revisar los índices y aplicar la migración prevista únicamente al destino confirmado, después del respaldo correspondiente. La auditoría de datos sin problemas no sustituye la revisión de duplicados e índices. No se ejecutó scripts/migrate_security_indexes.py en esta fase.
3. Ejecutar el ensayo aislado de Mongo y el recorrido real API/navegador: login, sesiones cliente/equipo, expiración/logout, aislamiento de propietarios, carga de imagen, guardar/recargar, conflicto de edición, preview y publicación.
4. Probar Webpay en UAT: aprobación, rechazo, cancelación, timeout, reintentos y retorno repetido, con una sola publicación y recibo; verificar coherencia con el portal de integración. No activar cobros productivos como parte de estas pruebas.
5. Subir un asset ficticio, reiniciar/reemplazar la instancia y comprobar URL/checksum. Restaurar Mongo/assets en un destino aislado y registrar RPO/RTO medidos. Conservar evidencia y un procedimiento de rollback verificable.
6. Verificar reconciliación de snapshots tras un resultado de transporte incierto y revisar logs del entorno sin exposición de secretos. Confirmar CI y artefacto desplegado antes de promover una versión.

Render y MongoDB Atlas tienen integraciones disponibles, aún sin instalación/conexión confirmada. También se puede continuar con una configuración de staging proporcionada por el operador. El acceso de lectura a Mongo ya comprobado no proporciona control del hosting, los volúmenes ni los respaldos.

## Verificación del código añadido

Lint y formato de app/scripts/tests aprobados; mypy estricto de los ocho módulos de contratos aprobado; **467 pruebas offline aprobadas sin advertencias**. Los 13 casos nuevos verifican guardas de aislamiento/producción, rechazo de bases existentes, redacción de errores, separación entre TLS y permisos de índices, interpretación del plan ganador y resumen de auditoría sin identificadores. Estas pruebas protegen las herramientas; no sustituyen su ejecución en el entorno real.

Para continuar falta confirmar staging o el uso de la configuración local con una base de pruebas aislada. La pregunta sobre ese destino sigue pendiente.
