import pytest
from test_pricing_catalog import InMemoryPricingRepository

from app.core.errors import NuvlyError
from app.modules.pricing.schemas import PricingCalculateRequest, PricingPlanUpdate, PricingVariantUpdate
from app.modules.pricing.service import (
    CatalogService,
    PricingCalculatorService,
    PricingComponentService,
    PricingPlanService,
    PricingSummaryService,
    ensure_pricing_seed,
)


def setup_catalog():
    repo = InMemoryPricingRepository()
    ensure_pricing_seed(repository=repo)
    service = PricingComponentService(repository=repo)
    component = next(c for c in service.list(product_type="website", active=True) if c["variants"])
    return repo, service, component, component["variants"][0]


@pytest.mark.parametrize(
    "minimum,expected",
    [
        ("plus", ["included", "included", "included"]),
        ("pro", ["blocked", "included", "included"]),
        ("custom", ["blocked", "blocked", "included"]),
    ],
)
@pytest.mark.parametrize("mode", ["included", "extra"])
def test_simple_rule_reaches_catalog_and_summary(minimum, expected, mode):
    repo, service, component, variant = setup_catalog()
    service.update_variant(
        component["id"],
        variant["variantCode"],
        PricingVariantUpdate(**{**variant, "pricingMode": mode, "availableFromPlan": minimum, "extraPrice": 3500}),
    )
    for tier, status in zip(["plus", "pro", "custom"], expected):
        catalog = CatalogService(repository=repo).list_components_for_catalog("website", "corporate", tier)
        configured = next(c for c in catalog["components"] if c["componentCode"] == component["componentCode"])
        actual = next(v for v in configured["variants"] if v["variantCode"] == variant["variantCode"])
        expected_status = mode if status == "included" else "blocked"
        assert actual["status"] == expected_status
        assert actual["extraPrice"] == (3500 if expected_status == "extra" else None)
    summary = PricingSummaryService(repository=repo).build_summary("website")
    row = next(c for c in summary["components"] if c["id"] == component["id"])
    matrix = next(v for v in row["variants"] if v["variantCode"] == variant["variantCode"])["matrix"]
    assert matrix[minimum]["status"] == mode


def test_paid_variant_is_charged_and_settings_survive_seed():
    repo, service, component, variant = setup_catalog()
    service.update_variant(
        component["id"],
        variant["variantCode"],
        PricingVariantUpdate(**{**variant, "pricingMode": "extra", "availableFromPlan": "plus", "extraPrice": 3500}),
    )
    plan_service = PricingPlanService(repository=repo)
    plan = plan_service.find_by_tier("website", "plus")
    plan_service.update(
        plan["id"],
        PricingPlanUpdate(**{**plan, "basePrice": 11000, "basePriceMonthly": 11000, "basePriceYearly": 120000}),
    )
    ensure_pricing_seed(repository=repo)
    configured = next(v for v in service.get(component["id"])["variants"] if v["variantCode"] == variant["variantCode"])
    assert configured["pricingMode"] == "extra" and configured["extraPrice"] == 3500
    assert plan_service.get(plan["id"])["basePriceYearly"] == 120000
    result = PricingCalculatorService(repository=repo).calculate(
        PricingCalculateRequest(
            productType="website",
            templateCategory="corporate",
            planTier="plus",
            selectedComponentExtras=[
                {"componentCode": component["componentCode"], "variantCode": variant["variantCode"]}
            ],
        )
    )
    assert result["componentExtrasTotal"] == 3500
    assert result["total"] == 14500


def test_free_ignores_old_extra_price_and_inactive_stays_inactive():
    repo, service, component, variant = setup_catalog()
    saved = service.update_variant(
        component["id"],
        variant["variantCode"],
        PricingVariantUpdate(
            **{**variant, "active": False, "pricingMode": "included", "availableFromPlan": "plus", "extraPrice": 9999}
        ),
    )
    actual = next(v for v in saved["variants"] if v["variantCode"] == variant["variantCode"])
    assert actual["extraPrice"] == 0 and not actual["canBeExtraInPlans"]
    catalog = CatalogService(repository=repo).list_components_for_catalog("website", "corporate", "plus")
    row = next(c for c in catalog["components"] if c["componentCode"] == component["componentCode"])
    assert next(v for v in row["variants"] if v["variantCode"] == variant["variantCode"])["status"] == "inactive"


@pytest.mark.parametrize(
    "changes",
    [
        {"pricingMode": "extra", "availableFromPlan": "plus", "extraPrice": 0},
        {"pricingMode": "included", "availableFromPlan": None},
    ],
)
def test_invalid_rule_does_not_replace_variant(changes):
    repo, service, component, variant = setup_catalog()
    with pytest.raises(NuvlyError):
        service.update_variant(component["id"], variant["variantCode"], PricingVariantUpdate(**{**variant, **changes}))
    assert service.get(component["id"])["variants"][0] == variant
