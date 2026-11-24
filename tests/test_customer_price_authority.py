import pytest
from test_payments_flow import InMemoryDomainRepository, _create_customer_invitation_project

from app.core.errors import NuvlyError
from app.modules.domain.schemas import CustomerInvitationUpdate, PublishRequest
from app.modules.domain.services import CUSTOMER_INVITATION_CONFIG, CustomerProjectService
from app.modules.payments.schemas import CheckoutPreviewRequest
from app.modules.payments.service import PaymentService


def invitation():
    repo = InMemoryDomainRepository()
    project = _create_customer_invitation_project(repo)
    project["ownerId"] = "owner"
    repo.replace_document(
        CUSTOMER_INVITATION_CONFIG.collection, project["id"], project, "missing", "missing", "duplicate"
    )
    return repo, CustomerProjectService(CUSTOMER_INVITATION_CONFIG, repository=repo), project


def test_customer_cannot_change_authoritative_invitation_price():
    repo, service, project = invitation()
    request = CheckoutPreviewRequest(projectId=project["id"], projectType="invitation")
    before = PaymentService(repository=repo).preview_checkout(request)
    saved = service.update_for_owner(
        project["id"],
        CustomerInvitationUpdate(
            title=project["title"],
            expectedUpdatedAt=project["updatedAt"],
            metadata={"basePrice": 1, "basePriceSource": "manual", "privateNote": "kept"},
        ),
        owner_id="owner",
    )
    assert saved["metadata"]["privateNote"] == "kept"
    assert saved["metadata"]["basePrice"] == project["metadata"]["basePrice"]
    assert PaymentService(repository=repo).preview_checkout(request)["amount"] == before["amount"]


def test_customer_publish_cannot_override_price():
    repo, service, project = invitation()
    with pytest.raises(NuvlyError) as exc:
        service.publish_for_owner(
            project["id"], owner_id="owner", publish_request=PublishRequest(priceMode="manual", basePrice=1)
        )
    assert exc.value.code == "CUSTOMER_PRICE_OVERRIDE_FORBIDDEN"
    assert not repo.collections.get(CUSTOMER_INVITATION_CONFIG.snapshot_collection)


def test_paid_customer_cannot_add_unpurchased_extra():
    repo, service, project = invitation()
    repo.update_document_fields(
        CUSTOMER_INVITATION_CONFIG.collection, project["id"], {"payment": {"status": "paid"}}, "missing", "missing"
    )
    with pytest.raises(NuvlyError) as exc:
        service.update_for_owner(
            project["id"],
            CustomerInvitationUpdate(
                title=project["title"],
                expectedUpdatedAt=project["updatedAt"],
                selectedComponentExtras=[{"componentCode": "hero", "variantCode": "premium", "extraPrice": 1}],
            ),
            owner_id="owner",
        )
    assert exc.value.code == "PAID_EXTRAS_IMMUTABLE"
