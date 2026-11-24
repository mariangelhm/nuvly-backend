# Cobro productivo: habilitación controlada

La implementación local soporta Webpay Plus productivo, separado de UAT. Está
desactivado por defecto. Mercado Pago conserva su circuito de pruebas; no se ha
habilitado su cobro productivo. Nunca usar credenciales reales en tests ni repositorio.

El operador configura en el gestor de secretos del despliegue:

- `PAYMENTS_ENVIRONMENT=production`
- `PAYMENTS_PRODUCTION_ENABLED=true` solo después de aprobar la validación operativa.
- `TRANSBANK_COMMERCE_CODE` y `TRANSBANK_API_KEY` emitidos para el comercio productivo.
- `PUBLIC_BASE_URL` y `FRONTEND_PUBLIC_BASE_URL` HTTPS del entorno correspondiente.

Las claves públicas de integración no se aceptan como credenciales productivas.
El proveedor disponible y las etiquetas del checkout reflejan el ambiente. El
backend verifica la orden, sesión, token y monto mediante la API del proveedor;
visitar una URL nunca basta para aprobar un pago. Los registros de UAT no se pueden
leer/confirmar mediante el adaptador productivo ni habilitan publicación en producción.

Validación pendiente en entorno autorizado: aprobación, rechazo, cancelación,
timeout, reintentos y retorno repetido; comparar importe/moneda/orden con el portal
del comercio, confirmar una sola publicación y recibo, verificar que secretos no
aparezcan en logs y comprobar rollback desactivando cobros nuevos sin perder acceso
al historial. No se realizó cobro ni despliegue en esta implementación local.
Los tests simulan el proveedor y cubren confirmación repetida sin doble publicación.

Referencias oficiales consultadas:

- [API REST Webpay Plus](https://github.com/TransbankDevelopers/transbank-developers-docs/blob/master/referencia/webpay/README.md): distingue hosts y credenciales de integración/producción, creación y confirmación.
- [Notificaciones de Mercado Pago](https://www.mercadopago.cl/developers/es/docs/checkout-pro-preferences/additional-settings/optional-notifications): firma de notificaciones del circuito existente. La consulta de algunas páginas adicionales devolvió 403; Mercado Pago productivo queda fuera de esta habilitación.
