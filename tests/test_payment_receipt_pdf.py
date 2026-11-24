from copy import deepcopy
from io import BytesIO

from pypdf import PdfReader

from app.modules.payments.receipt_pdf import render_accepted_terms_pdf
from app.modules.payments.terms import website_terms_document


def sample_payment():
    document = website_terms_document()
    return {
        "id": "pay_pdf_test",
        "paymentId": "pay_pdf_test",
        "termsAcceptance": {
            "version": document["version"],
            "document": document,
            "projectId": "cweb_test",
            "projectTitle": "Construcción & diseño <Buildframe>",
            "customerEmail": "cliente@example.test",
            "acceptedAt": "2026-11-12T15:30:00+00:00",
            "planTier": "plus",
            "amount": 114900,
            "currency": "CLP",
            "withCustomDomain": True,
            "customDomain": None,
            "billingTerms": {
                "initialMonths": 12,
                "initialAmount": 99900,
                "renewalAmount": 9990,
                "renewalStartsMonth": 13,
            },
            "pricing": {
                "subtotalAmount": 114900,
                "discountAmount": 0,
                "discountCode": None,
                "customDomainSurcharge": 15000,
            },
        },
    }


def test_pdf_contains_accepted_version_full_conditions_and_commercial_record():
    payment = sample_payment()
    pdf = render_accepted_terms_pdf(payment)
    assert pdf.startswith(b"%PDF-")
    reader = PdfReader(BytesIO(pdf))
    text = "\n".join(page.extract_text() for page in reader.pages)
    for expected in [
        "pay_pdf_test",
        "Construcción & diseño <Buildframe>",
        "cliente@example.test",
        "$114.900 CLP",
        "$9.990 CLP",
        "Dominio propio por definir",
        "No acredita por sí sola un pago aprobado",
        payment["termsAcceptance"]["document"]["sha256"],
    ]:
        assert expected in text
    for section in payment["termsAcceptance"]["document"]["sections"]:
        assert section["title"] in text
        assert " ".join(section["text"].split()) in " ".join(text.split())
    assert reader.pages[0].mediabox.width > 590
    assert len(reader.pages) >= 2


def test_pdf_uses_archived_terms_without_mutating_them():
    payment = sample_payment()
    payment["termsAcceptance"]["version"] = "version-archivada"
    payment["termsAcceptance"]["document"].update(
        version="version-archivada",
        sections=[{"title": "Acuerdo anterior", "text": "Estas son las condiciones exactas aceptadas por el cliente."}],
    )
    before = deepcopy(payment)
    text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(render_accepted_terms_pdf(payment))).pages)
    assert "version-archivada" in text
    assert "Estas son las condiciones exactas aceptadas por el cliente." in text
    assert "10. Aceptación y copia" not in text
    assert payment == before
