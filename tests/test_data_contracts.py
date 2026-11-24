from copy import deepcopy

import pytest
from pydantic import TypeAdapter, ValidationError
from test_payments_flow import InMemoryDomainRepository, _create_customer_project

from app.core.errors import NuvlyError
from app.core.value_types import CLPAmount
from app.modules.discounts.service import DiscountCodeService
from app.modules.domain.normalizer import normalize_document
from app.modules.domain.schemas import CustomerWebsiteUpdate, InvitationTemplateCreate, WebsiteTemplateCreate
from app.modules.domain.services import CUSTOMER_WEBSITE_CONFIG, CustomerProjectService
from app.modules.payments.schemas import CheckoutPreviewRequest
from app.modules.payments.service import PaymentService


@pytest.mark.parametrize("value", [-1, 1.5, "1.5", True, False, float("nan"), float("inf"), 2**53, None])
def test_invalid_clp_cannot_reach_payment_contracts(value):
    with pytest.raises(ValidationError):
        TypeAdapter(CLPAmount).validate_python(value)


@pytest.mark.parametrize("value", [1000, 1000.0, "1000", "1000.00"])
def test_integral_legacy_money_becomes_json_integer(value):
    parsed = TypeAdapter(CLPAmount).validate_python(value)
    assert type(parsed) is int and parsed == 1000
    assert TypeAdapter(CLPAmount).dump_json(parsed) == b"1000"


def test_discount_half_peso_uses_explicit_half_up_rule():
    assert DiscountCodeService.calculate_discount_amount(101, {"discountType": "percentage", "value": 50}) == 51
    assert DiscountCodeService.calculate_discount_amount(101, {"discountType": "fixed", "value": 500}) == 101


@pytest.mark.parametrize("timestamp", ["2026-11-24", "2026-11-24T10:00:00", "not-a-date", "2026-02-30T10:00:00Z"])
def test_invalid_revision_dates_rejected_at_boundary(timestamp):
    with pytest.raises(ValidationError):
        CustomerWebsiteUpdate(title="Project", expectedUpdatedAt=timestamp)


def test_revision_keeps_exact_text_for_cas():
    timestamp = "2026-11-24T10:00:00.123000-03:00"
    payload = CustomerWebsiteUpdate(title="Project", expectedUpdatedAt=timestamp)
    assert payload.model_dump()["expectedUpdatedAt"] == timestamp


@pytest.mark.parametrize(
    "model,product,category",
    [
        (WebsiteTemplateCreate, "invitation", "corporate"),
        (InvitationTemplateCreate, "website", "wedding"),
        (WebsiteTemplateCreate, "website", "wedding"),
    ],
)
def test_product_and_category_must_match_endpoint(model, product, category):
    with pytest.raises(ValidationError):
        model(title="Template", productType=product, templateCategory=category)


def test_duplicate_extras_and_non_json_content_are_rejected():
    extra = {"componentCode": "hero", "variantCode": "premium"}
    with pytest.raises(ValidationError):
        CustomerWebsiteUpdate(title="Project", selectedComponentExtras=[extra, extra])
    with pytest.raises(ValidationError):
        CustomerWebsiteUpdate(title="Project", content={"invalid": object()})
    with pytest.raises(ValidationError):
        CustomerWebsiteUpdate(title="Project", content={"invalid": float("nan")})


def test_custom_block_fields_and_empty_values_survive_write_contract():
    block = {
        "id": "hero",
        "type": "hero",
        "variant": "custom",
        "label": "Original label",
        "customField": {"empty": "", "items": []},
        "props": {"title": ""},
        "enabled": False,
    }
    payload = CustomerWebsiteUpdate(title="Project", blocks=[block])
    saved = payload.model_dump(exclude_unset=True)["blocks"][0]
    assert saved == block


def test_legacy_adaptation_adds_version_without_mutating_document():
    repo = InMemoryDomainRepository()
    project = _create_customer_project(repo)
    project.pop("schemaVersion", None)
    original = deepcopy(project)
    assert normalize_document(project, "customerStatus")["schemaVersion"] == 1
    assert project == original
    with pytest.raises(NuvlyError) as error:
        normalize_document({**project, "schemaVersion": 999}, "customerStatus")
    assert error.value.code == "UNSUPPORTED_SCHEMA_VERSION"


@pytest.mark.parametrize("parents", [("linked", "linked"), ("second", "linked")])
def test_page_parents_cannot_contain_self_or_indirect_cycles(parents):
    repo = InMemoryDomainRepository()
    project = _create_customer_project(repo)
    project["pages"] = [
        {"id": "main", "kind": "primary", "title": "Main", "path": "/", "blocks": []},
        {
            "id": "linked",
            "kind": "linked",
            "title": "Linked",
            "path": "/linked",
            "slug": "linked",
            "parentPageId": parents[0],
            "blocks": [],
        },
        {
            "id": "second",
            "kind": "linked",
            "title": "Second",
            "path": "/second",
            "slug": "second",
            "parentPageId": parents[1],
            "blocks": [],
        },
    ]
    with pytest.raises(NuvlyError) as error:
        normalize_document(project, "customerStatus")
    assert error.value.code == "PAGE_PARENT_CYCLE"


@pytest.mark.parametrize("status", ["paid", "payment_failed"])
def test_customer_cannot_assign_payment_owned_states(status):
    repo = InMemoryDomainRepository()
    project = _create_customer_project(repo)
    project["ownerId"] = "owner"
    repo.replace_document("customer_websites", project["id"], project, "missing", "missing", "duplicate")
    service = CustomerProjectService(CUSTOMER_WEBSITE_CONFIG, repository=repo)
    with pytest.raises(NuvlyError) as error:
        service.update_status_for_owner(project["id"], status, "forged-actor", None, owner_id="owner")
    assert error.value.code == "SERVER_MANAGED_STATUS"
    assert service.get(project["id"])["customerStatus"] == project["customerStatus"]


def test_fractional_legacy_catalog_cannot_be_silently_truncated_at_gateway():
    repo = InMemoryDomainRepository()
    project = _create_customer_project(repo)
    for plan in repo.collections["pricing_plans"]:
        if plan["productType"] == "website" and plan["tier"] == project["planTier"]:
            plan["basePriceYearly"] = 1000.5
    with pytest.raises(NuvlyError) as error:
        PaymentService(repo).preview_checkout(CheckoutPreviewRequest(projectType="website", projectId=project["id"]))
    assert error.value.code == "INVALID_CLP_AMOUNT"


def test_read_only_audit_detects_bad_prices_and_dates_without_interpreting_editor_text():
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "data_audit", Path(__file__).parents[1] / "scripts/audit_data_contracts.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    document = {"amount": 1000.5, "createdAt": "yesterday", "content": {"amount": "A beautiful day"}}
    original = deepcopy(document)
    issues = module.audit_document("payments", document)
    assert {i["code"] for i in issues} == {"INVALID_CLP_AMOUNT", "INVALID_TIMESTAMP"}
    assert len(issues) == 2 and document == original


def test_unknown_persisted_state_is_not_silently_accepted():
    repo = InMemoryDomainRepository()
    project = _create_customer_project(repo)
    project["customerStatus"] = "invented"
    with pytest.raises(NuvlyError) as error:
        normalize_document(project, "customerStatus")
    assert error.value.code == "INVALID_DOCUMENT_STATUS"


@pytest.mark.parametrize("path", ["//outside.test/path", "/foo/../bar", "/foo?secret=1", "/foo#bar"])
def test_page_paths_are_local_and_unambiguous(path):
    repo = InMemoryDomainRepository()
    project = _create_customer_project(repo)
    project["pages"][0]["path"] = path
    with pytest.raises(NuvlyError) as error:
        normalize_document(project, "customerStatus")
    assert error.value.code == "INVALID_PAGE_PATH"
