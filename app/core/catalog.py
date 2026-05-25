from typing import Literal


ProductType = Literal["website", "invitation"]
PlanTier = Literal["essential", "plus", "pro", "custom"]
VariantLevel = Literal["core", "advanced", "premium"]
WebsiteTemplateCategory = Literal[
    "construction",
    "beauty",
    "technical_services",
    "restaurant",
    "portfolio",
    "corporate",
    "health",
    "education",
]
InvitationTemplateCategory = Literal[
    "wedding",
    "birthday",
    "baby_shower",
    "graduation",
    "corporate_event",
    "baptism",
]
TemplateCategoryCode = WebsiteTemplateCategory | InvitationTemplateCategory

PRODUCT_TYPES: tuple[ProductType, ...] = ("website", "invitation")
PLAN_TIERS: tuple[PlanTier, ...] = ("essential", "plus", "pro", "custom")
VARIANT_LEVELS: tuple[VariantLevel, ...] = ("core", "advanced", "premium")
WEBSITE_TEMPLATE_CATEGORIES: tuple[WebsiteTemplateCategory, ...] = (
    "construction",
    "beauty",
    "technical_services",
    "restaurant",
    "portfolio",
    "corporate",
    "health",
    "education",
)
INVITATION_TEMPLATE_CATEGORIES: tuple[InvitationTemplateCategory, ...] = (
    "wedding",
    "birthday",
    "baby_shower",
    "graduation",
    "corporate_event",
    "baptism",
)
VALID_PRODUCT_TYPES: set[str] = set(PRODUCT_TYPES)
VALID_PLAN_TIERS: set[str] = set(PLAN_TIERS)
VALID_VARIANT_LEVELS: set[str] = set(VARIANT_LEVELS)
VALID_TEMPLATE_CATEGORIES: set[str] = set(WEBSITE_TEMPLATE_CATEGORIES) | set(INVITATION_TEMPLATE_CATEGORIES)
LEGACY_VARIANT_LEVEL_MAP: dict[str, VariantLevel] = {
    "basic": "core",
    "pro": "advanced",
    "premium": "premium",
    "core": "core",
    "advanced": "advanced",
}
DEFAULT_TEMPLATE_CATEGORY_BY_PRODUCT_TYPE: dict[ProductType, TemplateCategoryCode] = {
    "website": "corporate",
    "invitation": "wedding",
}
DEFAULT_PLAN_TIER_BY_PRODUCT_TYPE: dict[ProductType, PlanTier] = {
    "website": "plus",
    "invitation": "plus",
}
VARIANT_LEVEL_RULES: dict[VariantLevel, dict[str, list[str]]] = {
    "core": {
        "includedInPlans": ["essential", "plus", "pro"],
        "canBeExtraInPlans": [],
    },
    "advanced": {
        "includedInPlans": ["plus", "pro"],
        "canBeExtraInPlans": [],
    },
    "premium": {
        "includedInPlans": ["pro"],
        "canBeExtraInPlans": ["plus"],
    },
}


def normalize_variant_level(value: str | None, default: VariantLevel = "core") -> VariantLevel:
    if value is None:
        return default
    normalized = LEGACY_VARIANT_LEVEL_MAP.get(value.strip().lower())
    return normalized or default


def infer_variant_level_from_plan_rules(included_in_plans: list[str], can_be_extra_in_plans: list[str]) -> VariantLevel:
    included = set(included_in_plans)
    extra = set(can_be_extra_in_plans)
    if "essential" in included:
        return "core"
    if "plus" in included:
        return "advanced"
    if "plus" in extra or "pro" in included or "custom" in included:
        return "premium"
    return "core"


def normalize_product_type(value: str | None, default: ProductType) -> ProductType:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized == "web":
        return "website"
    if normalized == "invitation":
        return "invitation"
    return default


def normalize_plan_tier(value: str | None, default: PlanTier = "plus") -> PlanTier:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in VALID_PLAN_TIERS:
        return normalized  # type: ignore[return-value]
    return default


def normalize_template_category(value: str | None, product_type: ProductType) -> TemplateCategoryCode:
    if value is None:
        return DEFAULT_TEMPLATE_CATEGORY_BY_PRODUCT_TYPE[product_type]
    normalized = value.strip().lower()
    allowed = WEBSITE_TEMPLATE_CATEGORIES if product_type == "website" else INVITATION_TEMPLATE_CATEGORIES
    if normalized in allowed:
        return normalized  # type: ignore[return-value]
    return DEFAULT_TEMPLATE_CATEGORY_BY_PRODUCT_TYPE[product_type]
