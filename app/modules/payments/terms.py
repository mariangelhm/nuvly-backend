"""Versioned website conditions. Keep the accepted document with each payment."""

import hashlib
import json
from copy import deepcopy

from app.core.errors import NuvlyError

WEBSITE_TERMS = {
    "version": "website-2026-11-12",
    "title": "Términos y condiciones del servicio de páginas web Nuvly",
    "effectiveDate": "2026-11-12",
    "sections": [
        {
            "title": "1. Servicio contratado",
            "text": "Nuvly ofrece acceso a su editor, uso de la plantilla y componentes del plan, alojamiento, conexión HTTPS y soporte de funcionamiento. El resumen del pago identifica el proyecto, el plan, los precios y los servicios adicionales contratados. No se promete una cantidad de visitas, ventas o resultados comerciales.",
        },
        {
            "title": "2. Primer año y continuidad",
            "text": "El pago inicial cubre 12 meses completos de servicio desde la publicación de la web. Durante ese período no se cobra una mensualidad adicional por el plan. Desde el mes 13, la continuidad se contrata por períodos mensuales al precio de renovación informado en el checkout. Este pago no autoriza cargos recurrentes automáticos: cada renovación requiere un nuevo pago. Cualquier futura modalidad de cobro automático requerirá información y autorización específicas.",
        },
        {
            "title": "3. Precios y servicios adicionales",
            "text": "El total y los descuentos se muestran antes de pagar. El diseño a medida, los cambios realizados por nuestro equipo y los extras no incluidos requieren una cotización y aceptación adicionales. Las modificaciones de precio se informarán antes de una nueva contratación y no alterarán un período ya pagado.",
        },
        {
            "title": "4. Dominio propio",
            "text": "El dominio es opcional y puede elegirse después del pago. Si contratas su configuración, Nuvly te contactará para asesorarte y conectarlo a tu web. La compra y renovación del dominio se pagan por separado del alojamiento y de su configuración. El dominio debe registrarse a nombre del cliente; terminar el servicio de Nuvly no transfiere su titularidad a Nuvly.",
        },
        {
            "title": "5. Cancelación por el cliente",
            "text": "Puedes solicitar que no se renueve el servicio antes del siguiente período escribiendo a contacto@nuvly.com desde el correo de tu cuenta e identificando tu proyecto. Tu web seguirá disponible hasta el fin del período pagado, salvo que solicites su retiro anticipado. La cancelación de futuras renovaciones no elimina tus derechos legales sobre devoluciones o incumplimientos.",
        },
        {
            "title": "6. No renovación por Nuvly",
            "text": "Nuvly podrá comunicar que no ofrecerá nuevos períodos por cierre del servicio, retiro del producto o una imposibilidad técnica o legal objetiva de continuar. Lo informará al correo de la cuenta con al menos 60 días de anticipación a la fecha de término y respetará los períodos ya pagados. Este aviso no autoriza a interrumpir arbitrariamente un contrato vigente ni a discriminar injustificadamente al cliente. Durante el aviso se coordinará la entrega del contenido aportado por el cliente y la desconexión o traslado de su dominio. La licencia de la plataforma y sus plantillas no implica entrega del código fuente ni una copia ejecutable en otro alojamiento.",
        },
        {
            "title": "7. Impago y uso indebido",
            "text": "Si no se paga un nuevo período, el servicio podrá dejar de estar publicado al terminar el período vigente. El cliente debe aportar contenido que tenga derecho a utilizar y no usar la web para actividades ilícitas, fraude o ataques informáticos. Ante un incumplimiento se informará la causa y, cuando sea subsanable, se dará un plazo razonable para corregirlo. Podrán aplicarse medidas inmediatas cuando sean necesarias para cumplir una orden legal o detener un riesgo grave para la seguridad, informando al cliente tan pronto sea posible.",
        },
        {
            "title": "8. Contenido y datos",
            "text": "El cliente conserva los derechos sobre sus textos, imágenes y otros contenidos. Autoriza a Nuvly a tratarlos únicamente para prestar el servicio y cumplir obligaciones legales. Antes del término puede solicitar una copia del contenido que aportó. Las solicitudes de acceso, corrección o eliminación de datos se reciben en contacto@nuvly.com y se atienden conforme a la legislación aplicable. No se garantiza conservar indefinidamente una web después de terminar el servicio.",
        },
        {
            "title": "9. Derechos del cliente",
            "text": "Estos términos no limitan los derechos irrenunciables establecidos por la legislación chilena, incluidos los que correspondan por retracto, incumplimiento o devolución. Para ejercerlos, solicitar asistencia o reclamar, escribe a contacto@nuvly.com indicando tu proyecto y pago. La aceptación de estos términos no constituye una renuncia a esos derechos ni obliga a un arbitraje exclusivo.",
        },
        {
            "title": "10. Aceptación y copia",
            "text": "Antes de pagar puedes leer y descargar estas condiciones. Al marcar la casilla se registra la versión aceptada, la fecha del servidor y la cuenta contratante junto al pago y su detalle. Puedes descargar la constancia desde la pantalla de pago. Una modificación posterior de estos términos no reemplaza la versión aceptada para un período ya contratado.",
        },
    ],
}


def website_terms_document():
    document = deepcopy(WEBSITE_TERMS)
    document["sha256"] = hashlib.sha256(
        json.dumps(WEBSITE_TERMS, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return document


def validate_terms_acceptance(payload):
    if payload.projectType != "website":
        return
    if payload.termsAccepted is not True:
        raise NuvlyError(
            "Debes aceptar los términos y condiciones antes de continuar al pago.", 422, "TERMS_ACCEPTANCE_REQUIRED"
        )
    if payload.termsVersion != WEBSITE_TERMS["version"]:
        raise NuvlyError(
            "Los términos se actualizaron. Vuelve a leerlos y acepta la versión vigente.", 422, "TERMS_VERSION_MISMATCH"
        )
