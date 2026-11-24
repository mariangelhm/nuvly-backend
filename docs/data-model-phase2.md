# Fase 2: contratos y modelo de datos

Fecha: 2026-11-24. Implementación verificada localmente; no se accedió ni modificó una base real.

## Contratos adoptados

- **Dinero CLP:** precios de planes, variantes, publicación manual y respuestas de checkout usan CLPAmount, un entero no negativo hasta 2^53-1 para intercambio exacto con JavaScript. Un valor histórico integral como 1000.0 o "1000.00" se acepta como 1000; fracciones, booleanos, negativos y valores no finitos se rechazan. No se redondean tarifas antiguas automáticamente.
- **Cálculo comercial:** checkout suma pesos enteros y valida también las tarifas leídas del repositorio antes de crear una transacción. Una tarifa antigua fraccionaria produce INVALID_CLP_AMOUNT en lugar de truncarse al enviarla al proveedor. El descuento porcentual se calcula con Decimal y ROUND_HALF_UP al peso: 50% de 101 descuenta 51. Esta regla sustituye el redondeo binario/half-even anterior, que podía descontar 50 en ese caso. Los recibos/reportes históricos conservan su información; no se reescribe el historial de pagos.
- **Fechas de entrada:** expectedUpdatedAt, selectedAt y vencimiento de descuentos se validan como fecha-hora ISO 8601 con zona horaria. La revisión expectedUpdatedAt conserva exactamente su representación y precisión: no se convierte a otra zona ni se formatea antes de compararla en Mongo. Las fechas de eventos siguen siendo contenido editorial y no se convierten a UTC.
- **Datos configurables:** los mapas declarados de contenido, estilos, bloques y páginas usan valores JSON recursivos; rechazan objetos Python arbitrarios y números no finitos. Se conservan campos adicionales de bloques, textos vacíos, listas vacías y elementos desactivados. No se impone un esquema cerrado a cada variante visual.
- **Identidad comercial:** los DTO de webs aceptan productType=website y los de invitaciones productType=invitation. La categoría debe pertenecer al producto y no pueden repetirse pares componentCode/variantCode entre extras seleccionados.
- **Páginas:** kind admite primary/linked. Se mantienen las reglas existentes de página primaria única, ids/rutas/slugs únicos y padres existentes; ahora se rechazan ciclos directos/indirectos y rutas con navegación relativa, query, fragmento o destino externo de tipo //host.
- **Estados:** DTO y normalizador comparten el vocabulario en domain/states.py. Un documento con estado desconocido falla explícitamente. El propietario no puede asignarse paid/payment_failed mediante el endpoint de estado; la publicación mantiene su verificación de pago. El actor del cambio solicitado por cliente se obtiene de owner_id autenticado.
- **Versión:** documentos normalizados y nuevos snapshots incluyen schemaVersion=1, distinta de version (número de publicación). Sin schemaVersion o con 0 se adaptan al contrato actual en memoria. Versiones desconocidas fallan con UNSUPPORTED_SCHEMA_VERSION. Se conserva la adaptación previa blocks/metadata.linkedPages -> pages.

## Compatibilidad y revisión de datos antiguos

No se ejecuta una migración masiva ni se reescriben proyectos durante una lectura. El normalizador trabaja sobre una copia; la versión adaptada se persiste al realizar una escritura normal. Los datos heredados que cumplan el contrato mantienen su contenido.

Antes de desplegar, ejecutar en staging desde el backend:

```powershell
python scripts/audit_data_contracts.py
```

Es una auditoría de solo lectura que recorre templates, proyectos, precios, pagos y descuentos. Emite colección, identificador y campos/códigos con problemas; no imprime contenido editorial ni datos de contacto. Devuelve 1 si detecta problemas y 0 en caso contrario. Incluye fechas estructurales, importes, estado, versión y estructura de páginas; no intenta interpretar como dinero propiedades editoriales que casualmente se llamen amount.

Resolver explícitamente las tarifas fraccionarias, fechas ambiguas, estados inválidos y ciclos encontrados antes de promover el backend. Los modelos de respuesta también exigen importes válidos; registros antiguos inválidos pueden necesitar corrección para que su lectura tipada funcione. Respaldar y aprobar las correcciones concretas antes de aplicarlas. El script no modifica documentos.

Se mantienen las fechas ISO almacenadas para conservar compatibilidad y revisiones CAS. No se convierten en esta fase a fechas BSON los campos existentes, ni se añaden índices TTL sobre strings. Una conversión BSON requiere una migración separada y pruebas con Mongo real; no se declara realizada. La auditoría tampoco certifica todas las reglas de negocio ni revisa credenciales de sesiones.

## Verificación

Backend: 454 pruebas aprobadas, incluyendo 36 casos nuevos de contrato y regresiones de pagos, publicación, privacidad, concurrencia y round-trip. Frontend: 132 casos unitarios y 99 regresiones aprobados, sin cambios de código frontend en esta fase. Se mantienen seis advertencias de deprecación de HTTP 422 ya existentes.

La prueba con datos y Mongo reales, la auditoría del entorno y la comprobación completa de pagos corresponden a la fase 5. No se realizó despliegue ni cobro.
