"""Render the immutable accepted terms, never the currently published version."""

from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _register_fonts():
    fonts = Path(reportlab.__file__).parent / "fonts"
    if "NuvlyReceipt" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("NuvlyReceipt", str(fonts / "Vera.ttf")))
        pdfmetrics.registerFont(TTFont("NuvlyReceiptBold", str(fonts / "VeraBd.ttf")))


def render_accepted_terms_pdf(payment):
    acceptance = payment["termsAcceptance"]
    document = acceptance["document"]
    _register_fonts()
    output = BytesIO()
    navy = colors.HexColor("#172D4B")
    muted = colors.HexColor("#53657E")
    body = ParagraphStyle(
        "body", fontName="NuvlyReceipt", fontSize=9, leading=14, textColor=navy, spaceAfter=10, alignment=TA_LEFT
    )
    heading = ParagraphStyle(
        "heading",
        parent=body,
        fontName="NuvlyReceiptBold",
        fontSize=12,
        leading=17,
        spaceBefore=12,
        spaceAfter=6,
        keepWithNext=True,
    )
    title = ParagraphStyle("title", parent=heading, fontSize=23, leading=29, spaceAfter=12)
    small = ParagraphStyle("small", parent=body, fontSize=8, leading=12, textColor=muted)
    cell = ParagraphStyle("cell", parent=body, fontSize=9, leading=13, spaceAfter=0)

    def paragraph(value, style=body):
        return Paragraph(escape(str(value or "")).replace("\n", "<br/>"), style)

    def money(value):
        return f"${float(value or 0):,.0f}".replace(",", ".") + " CLP"

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#DCE4EF"))
        canvas.line(48, 43, A4[0] - 48, 43)
        canvas.setFont("NuvlyReceipt", 7)
        canvas.setFillColor(muted)
        canvas.drawString(48, 29, "Nuvly | " + document["version"])
        canvas.drawRightString(A4[0] - 48, 29, f"Página {doc.page}")
        canvas.restoreState()

    story = [
        paragraph("NUVLY", heading),
        paragraph("Condiciones aceptadas", title),
        paragraph("Constancia de aceptación", heading),
    ]
    rows = [
        ("Referencia de pago", payment.get("paymentId") or payment["id"]),
        ("Proyecto", acceptance.get("projectTitle") or acceptance.get("projectId")),
        ("Cliente", acceptance.get("customerEmail") or acceptance.get("customerId")),
        ("Fecha de aceptación", acceptance.get("acceptedAt")),
        ("Versión aceptada", acceptance["version"]),
        (
            "Plan",
            {"essential": "Básico", "plus": "Básico", "pro": "Avanzado", "custom": "Personalizado"}.get(
                acceptance.get("planTier"), acceptance.get("planTier") or "Según contratación"
            ),
        ),
        ("Total del checkout", money(acceptance.get("amount"))),
        (
            "Publicación",
            (acceptance.get("customDomain") or "Dominio propio por definir")
            if acceptance.get("withCustomDomain")
            else "URL Nuvly",
        ),
    ]
    billing = acceptance.get("billingTerms") or {}
    if billing:
        rows.extend(
            [
                ("Período inicial", f"{billing['initialMonths']} meses"),
                ("Pago inicial del plan", money(billing["initialAmount"])),
                (
                    "Continuidad",
                    f"{money(billing['renewalAmount'])} al mes desde el mes {billing['renewalStartsMonth']}",
                ),
            ]
        )
    pricing = acceptance.get("pricing") or {}
    if pricing:
        rows.extend(
            [
                ("Subtotal", money(pricing.get("subtotalAmount"))),
                ("Descuento", money(pricing.get("discountAmount"))),
                ("Código de descuento", pricing.get("discountCode") or "Sin descuento"),
                ("Configuración del dominio", money(pricing.get("customDomainSurcharge"))),
            ]
        )
    table = Table(
        [[paragraph(label, small), paragraph(value, cell)] for label, value in rows],
        colWidths=[170, A4[0] - 266],
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.HexColor("#F3F7FE"), colors.white]),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.extend(
        [
            table,
            Spacer(1, 16),
            paragraph(
                "Esta constancia registra la aceptación de condiciones. No acredita por sí sola un pago aprobado ni reemplaza una boleta o factura.",
                small,
            ),
            PageBreak(),
            paragraph(document["title"], title),
            paragraph(f"Versión: {document['version']} | Vigencia: {document['effectiveDate']}", small),
        ]
    )
    for section in document["sections"]:
        story.extend([paragraph(section["title"], heading), paragraph(section["text"])])
    story.extend(
        [
            Spacer(1, 10),
            KeepTogether(
                [paragraph("Huella del documento aceptado (SHA-256)", small), paragraph(document.get("sha256"), small)]
            ),
        ]
    )
    SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=48,
        leftMargin=48,
        topMargin=40,
        bottomMargin=60,
        title="Nuvly - Condiciones aceptadas y constancia",
        author="Nuvly",
    ).build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
