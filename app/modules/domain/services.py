"""Compatibility imports for domain services. Implementations live by responsibility."""

from app.modules.domain.commercial_rules import CommercialRulesService
from app.modules.domain.configs import (
    CUSTOMER_INVITATION_CONFIG,
    CUSTOMER_WEBSITE_CONFIG,
    INVITATION_TEMPLATE_CONFIG,
    WEBSITE_TEMPLATE_CONFIG,
    CustomerConfig,
    TemplateConfig,
)
from app.modules.domain.customer_project_service import CustomerProjectService
from app.modules.domain.project_support import (
    COMMON_EXPERIENCE_FIELDS,
    PUBLIC_SLUG_PATTERN,
    SERVER_MANAGED_CUSTOMER_METADATA,
    SERVER_MANAGED_TEMPLATE_FIELDS,
    STATIC_UPLOAD_PREFIX,
    append_status_history,
    ensure_snapshot,
)
from app.modules.domain.project_support import (
    _decorate_public_media as _decorate_public_media,
)
from app.modules.domain.template_service import TemplateService

__all__ = [
    "COMMON_EXPERIENCE_FIELDS",
    "CUSTOMER_INVITATION_CONFIG",
    "CUSTOMER_WEBSITE_CONFIG",
    "CommercialRulesService",
    "CustomerConfig",
    "CustomerProjectService",
    "INVITATION_TEMPLATE_CONFIG",
    "PUBLIC_SLUG_PATTERN",
    "SERVER_MANAGED_CUSTOMER_METADATA",
    "SERVER_MANAGED_TEMPLATE_FIELDS",
    "STATIC_UPLOAD_PREFIX",
    "TemplateConfig",
    "TemplateService",
    "WEBSITE_TEMPLATE_CONFIG",
    "append_status_history",
    "ensure_snapshot",
]
