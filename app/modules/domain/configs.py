"""Immutable collection and entity configuration."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TemplateConfig:
    collection: str
    snapshot_collection: str
    source_type: str
    entity_kind: str
    experience_type: str
    id_prefix: str
    not_found_message: str
    not_found_code: str
    duplicate_message: str
    data_field: str


@dataclass(frozen=True)
class CustomerConfig:
    collection: str
    snapshot_collection: str
    source_type: str
    entity_kind: str
    id_prefix: str
    not_found_message: str
    not_found_code: str
    duplicate_message: str
    data_field: str
    template_config: TemplateConfig


INVITATION_TEMPLATE_CONFIG = TemplateConfig(
    collection="invitation_templates",
    snapshot_collection="invitation_template_snapshots",
    source_type="invitation_template",
    entity_kind="invitation",
    experience_type="invitation",
    id_prefix="itpl",
    not_found_message="Template de invitacion no encontrado.",
    not_found_code="INVITATION_TEMPLATE_NOT_FOUND",
    duplicate_message="Ya existe un template de invitacion con ese slug.",
    data_field="invitationData",
)


WEBSITE_TEMPLATE_CONFIG = TemplateConfig(
    collection="website_templates",
    snapshot_collection="website_template_snapshots",
    source_type="website_template",
    entity_kind="website",
    experience_type="web",
    id_prefix="wtpl",
    not_found_message="Template de website no encontrado.",
    not_found_code="WEBSITE_TEMPLATE_NOT_FOUND",
    duplicate_message="Ya existe un template de website con ese slug.",
    data_field="websiteData",
)


CUSTOMER_INVITATION_CONFIG = CustomerConfig(
    collection="customer_invitations",
    snapshot_collection="customer_invitation_snapshots",
    source_type="customer_invitation",
    entity_kind="invitation",
    id_prefix="cinv",
    not_found_message="Invitacion del cliente no encontrada.",
    not_found_code="CUSTOMER_INVITATION_NOT_FOUND",
    duplicate_message="Ya existe una invitacion del cliente con ese slug.",
    data_field="invitationData",
    template_config=INVITATION_TEMPLATE_CONFIG,
)


CUSTOMER_WEBSITE_CONFIG = CustomerConfig(
    collection="customer_websites",
    snapshot_collection="customer_website_snapshots",
    source_type="customer_website",
    entity_kind="website",
    id_prefix="cweb",
    not_found_message="Website del cliente no encontrado.",
    not_found_code="CUSTOMER_WEBSITE_NOT_FOUND",
    duplicate_message="Ya existe un website del cliente con ese slug.",
    data_field="websiteData",
    template_config=WEBSITE_TEMPLATE_CONFIG,
)
