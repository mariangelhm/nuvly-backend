from copy import deepcopy

import pytest
from pydantic import ValidationError
from test_payments_flow import InMemoryDomainRepository, _create_customer_invitation_project

from app.modules.domain.schemas import CustomerInvitationResponse, CustomerInvitationUpdate
from app.modules.domain.services import CUSTOMER_INVITATION_CONFIG, CustomerProjectService


@pytest.mark.parametrize(
    "component", ["romantic-motion", "editorial-luxury", "editorial-vogue", "ghibli-dream", "cyber-love-2077"]
)
def test_invitation_edit_save_reload_publish_preserves_render_contract(component):
    repo = InMemoryDomainRepository()
    project = _create_customer_invitation_project(repo)
    service = CustomerProjectService(CUSTOMER_INVITATION_CONFIG, repository=repo)
    content = {
        "base": {"coupleNames": "Canario & Contrato", "message": ""},
        "images": {"heroImage": "/assets/sample.png"},
        "templateComponent": component,
    }
    styles = {
        "fonts": {"bodyFont": "Georgia"},
        "themeTokens": {"accent": "#123456"},
        "manualColorOverrides": {"namesColor": True},
        "colors": {"namesColor": "#654321"},
    }
    blocks = deepcopy(project["blocks"])
    blocks[0]["enabled"] = False
    saved = service.update(
        project["id"],
        CustomerInvitationUpdate(
            title=project["title"],
            templateComponent=component,
            content=content,
            styles=styles,
            blocks=blocks,
        ),
    )
    reloaded = CustomerInvitationResponse.model_validate(service.get(project["id"])).model_dump(mode="json")
    assert reloaded["content"] == content
    assert reloaded["templateComponent"] == component
    for key, value in styles.items():
        assert reloaded["styles"][key] == value
    assert reloaded["blocks"][0]["enabled"] is False
    repo.update_document_fields(
        CUSTOMER_INVITATION_CONFIG.collection,
        project["id"],
        {"payment": {"status": "paid", "testMode": True}},
        "missing",
        "missing",
    )
    service.publish(project["id"])
    public = service.get_published_by_slug(project["publicSlug"])["snapshot"]
    assert public["content"] == content
    assert public["templateComponent"] == component
    assert public["styles"] == saved["styles"]
    assert public["blocks"][0]["enabled"] is False


@pytest.mark.parametrize(
    "patch", [{"content": []}, {"styles": {"fonts": []}}, {"unknownRenderField": "silently lost?"}]
)
def test_invalid_invitation_contract_is_rejected(patch):
    with pytest.raises(ValidationError):
        CustomerInvitationUpdate.model_validate({"title": "Test", **patch})
