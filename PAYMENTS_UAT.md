# Pagos de prueba de Nuvly

## Estado

El checkout conecta con dos proveedores: Mercado Pago Checkout Pro y Webpay Plus de Transbank. Webpay y Transbank son la misma opción. La integración está limitada a UAT: no se admiten cobros de producción. Las aprobaciones de prueba se guardan en el registro de pago, sin marcar el proyecto como pagado, emitir comprobantes reales ni publicarlo.

## Para empezar sin cuentas

Webpay Plus utiliza las credenciales públicas del ambiente de integración publicadas en el SDK oficial. No se necesita contratar producción para probar. Mercado Pago permanecerá visible pero deshabilitado hasta configurar las credenciales de una aplicación de prueba.

Reinicia el backend después de actualizar el código. El entorno local puede usar:

```dotenv
APP_ENV=development
PAYMENTS_ENVIRONMENT=integration
PUBLIC_BASE_URL=http://localhost:8000
FRONTEND_PUBLIC_BASE_URL=http://localhost:5173
```

Desde un proyecto del cliente, termina la edición y abre el checkout. Selecciona **Webpay Plus · Transbank**, continúa y pulsa **Probar pago**. La aplicación envía el token por POST a `webpay3gint.transbank.cl`; los datos de tarjeta se ingresan en Webpay, nunca en Nuvly.

Tarjeta pública de prueba aprobada:
- Visa: `4051 8856 0044 6623`
- CVV: `123`
- Vencimiento: una fecha futura.
- Autenticación bancaria simulada: RUT `11.111.111-1`, clave `123`.

Tarjeta de prueba rechazada: Mastercard `5186 0595 5959 0568`, CVV `123`.

Después del retorno, Nuvly confirma por API, coteja el token, el número de orden, la sesión y el monto. La pantalla distingue aprobación, rechazo y pago pendiente. Volver a abrir el resultado no crea una aprobación manual.

## Configurar Mercado Pago cuando tengas la cuenta

1. En Mercado Pago Developers Chile, crea una aplicación de **Checkout Pro**. Esta implementación utiliza la API de preferencias.
2. Obtén el Access Token de prueba y configura privadamente `MERCADOPAGO_TEST_ACCESS_TOKEN` en el entorno del backend. No lo incluyas en el frontend, el repositorio ni el chat. Si las credenciales de un vendedor de prueba comienzan por `APP_USR`, la API comprueba que la cuenta tenga la etiqueta `test_user` y pertenezca a Chile (`MLC`). Las credenciales de vendedores reales se rechazan.
3. Reinicia el backend y usa las cuentas y tarjetas de prueba indicadas para Checkout Pro. Nuvly abre únicamente `sandbox_init_point`, no el checkout productivo.

La aprobación solo se acepta al consultar un pago con `live_mode=false`, monto/moneda/referencia coincidentes. Los parámetros `status=approved` de una URL no confirman pagos.

## UAT público y notificaciones

Para una prueba desde otro equipo o con webhooks, configura orígenes HTTPS públicos de frontend y backend. Ajusta CORS para el frontend UAT. No apuntes callbacks a localhost si quienes deben recibirlos están en otro equipo.

- Retorno Webpay (GET o POST): `/api/payments/return/transbank/{paymentId}`.
- Retorno Mercado Pago: `/api/payments/return/mercadopago/{paymentId}`.
- Webhook Mercado Pago: `/api/payments/webhooks/mercadopago`.
- Configura `MERCADOPAGO_TEST_WEBHOOK_SECRET` solo si activas notificaciones; se verifica HMAC, identificador y antigüedad de la firma antes de consultar la API.
- Webpay usa retorno y consulta/confirmación API, no el antiguo webhook manual.

Los endpoints de creación y consulta requieren sesión y pertenencia del proyecto al cliente. `/api/payments/providers` informa qué proveedores están disponibles sin exponer credenciales. El antiguo GET que marcaba un pago como aprobado fue reemplazado por consulta verificada.

## Verificación realizada

Se creó y consultó una transacción en la API pública de integración de Transbank, con monto ficticio de $1.000: estado inicial pendiente y host de integración confirmado. No se ingresaron tarjetas ni se realizó un cargo real. Las pruebas automatizadas cubren creación, verificación de monto/referencia, rechazos, firma, permisos y repetición del retorno. La compra completa en el formulario bancario queda por realizar; Mercado Pago no ha sido probado con credenciales reales de sandbox porque todavía no hay una aplicación configurada.

## Antes de producción

Este código bloquea producción deliberadamente. La habilitación futura requiere cuentas comerciales, credenciales de producción, tarifas acordadas, verificación integral de retornos y notificaciones, idempotencia/concurrencia, conciliación, devoluciones, y conexión de la aprobación real con publicación/facturación. No basta con cambiar una URL o una variable para cobrar dinero real.

Fuentes oficiales consultadas el 10 de noviembre de 2026:
- https://transbankdevelopers.com/documentacion/como_empezar
- https://transbankdevelopers.com/documentacion/webpay-plus
- https://github.com/TransbankDevelopers/transbank-sdk-python
- https://www.mercadopago.cl/developers/es/docs/checkout-pro-preferences/test-accounts
- https://www.mercadopago.cl/developers/en/reference/online-payments/checkout-pro-preferences/create-preference/post
