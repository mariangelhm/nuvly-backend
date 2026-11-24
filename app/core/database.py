from pymongo import ASCENDING, MongoClient
from pymongo.database import Database

from app.core.config import get_settings

_client: MongoClient | None = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = MongoClient(
            settings.mongodb_uri,
            serverSelectionTimeoutMS=20000,
            connectTimeoutMS=20000,
            socketTimeoutMS=20000,
            tls=True,
            tlsAllowInvalidCertificates=False,
            tlsAllowInvalidHostnames=False,
        )
    return _client


def get_database() -> Database:
    settings = get_settings()
    return get_client()[settings.mongodb_db_name]


def create_indexes() -> None:
    db = get_database()
    db.rate_limits.create_index([("expiresAt", ASCENDING)], expireAfterSeconds=0)
    db.operating_costs.create_index([("id", ASCENDING)], unique=True)
    db.operating_costs.create_index([("environment", ASCENDING), ("active", ASCENDING), ("incurredOn", ASCENDING)])
    db.analytics_events.create_index([("id", ASCENDING)], unique=True)
    db.analytics_events.create_index([("environment", ASCENDING), ("receivedAt", ASCENDING)])
    db.analytics_events.create_index([("sessionId", ASCENDING), ("receivedAt", ASCENDING)])
    db.analytics_events.create_index([("expiresAt", ASCENDING)], expireAfterSeconds=0)
    db.experience_metrics.create_index([("environment", ASCENDING), ("receivedAt", ASCENDING)])
    db.experience_metrics.create_index([("expiresAt", ASCENDING)], expireAfterSeconds=0)
    db.payments.create_index([("projectId", ASCENDING)])
    db.users.create_index([("id", ASCENDING)], unique=True)
    db.users.create_index([("emailNormalized", ASCENDING)], unique=True)
    db.users.create_index(
        [("providerLinks.google.subject", ASCENDING)],
        unique=True,
        partialFilterExpression={"providerLinks.google.subject": {"$type": "string"}},
    )
    db.auth_google_challenges.create_index([("tokenHash", ASCENDING)], unique=True)
    db.auth_google_challenges.create_index([("expiresAt", ASCENDING)], expireAfterSeconds=0)
    db.users.create_index([("active", ASCENDING)])
    db.users.create_index([("createdAt", ASCENDING)])
    db.users.create_index([("authProviders", ASCENDING)])
    db.auth_sessions.create_index([("id", ASCENDING)], unique=True)
    db.auth_sessions.create_index([("tokenHash", ASCENDING)], unique=True)
    db.auth_sessions.create_index([("userId", ASCENDING), ("active", ASCENDING)])
    db.auth_sessions.create_index([("expiresAt", ASCENDING)])
    db.password_reset_tokens.create_index([("id", ASCENDING)], unique=True)
    db.password_reset_tokens.create_index([("tokenHash", ASCENDING)], unique=True)
    db.password_reset_tokens.create_index([("userId", ASCENDING), ("usedAt", ASCENDING)])
    db.password_reset_tokens.create_index([("expiresAt", ASCENDING)])
    db.customer_invitations.create_index([("ownerId", ASCENDING)])
    db.customer_invitations.create_index([("ownerEmail", ASCENDING)])
    db.customer_websites.create_index([("ownerId", ASCENDING)])
    db.customer_invitations.create_index([("ownerId", ASCENDING), ("updatedAt", -1), ("id", ASCENDING)])
    db.customer_websites.create_index([("ownerId", ASCENDING), ("updatedAt", -1), ("id", ASCENDING)])
    db.customer_websites.create_index([("ownerEmail", ASCENDING)])
    db.invitation_templates.create_index([("slug", ASCENDING)], unique=True)
    db.invitation_templates.create_index([("templateStatus", ASCENDING)])
    db.invitation_templates.create_index([("updatedAt", ASCENDING)])
    db.invitation_templates.create_index([("metadata.catalogVisible", ASCENDING)])
    db.invitation_templates.create_index(
        [("productType", ASCENDING), ("planTier", ASCENDING), ("templateCategory", ASCENDING)]
    )
    db.website_templates.create_index([("slug", ASCENDING)], unique=True)
    db.website_templates.create_index([("templateStatus", ASCENDING)])
    db.website_templates.create_index([("updatedAt", ASCENDING)])
    db.website_templates.create_index([("metadata.catalogVisible", ASCENDING)])
    db.website_templates.create_index(
        [("productType", ASCENDING), ("planTier", ASCENDING), ("templateCategory", ASCENDING)]
    )
    db.customer_invitations.create_index([("slug", ASCENDING)])
    db.customer_invitations.create_index(
        [("publicSlug", ASCENDING)],
        unique=True,
        partialFilterExpression={"publicSlug": {"$type": "string"}},
    )
    db.customer_invitations.create_index([("customerStatus", ASCENDING)])
    db.customer_invitations.create_index([("updatedAt", ASCENDING)])
    db.customer_invitations.create_index(
        [("productType", ASCENDING), ("planTier", ASCENDING), ("templateCategory", ASCENDING)]
    )
    db.customer_websites.create_index([("slug", ASCENDING)])
    db.customer_websites.create_index(
        [("publicSlug", ASCENDING)],
        unique=True,
        partialFilterExpression={"publicSlug": {"$type": "string"}},
    )
    db.customer_websites.create_index([("customerStatus", ASCENDING)])
    db.customer_websites.create_index([("updatedAt", ASCENDING)])
    db.customer_websites.create_index(
        [("productType", ASCENDING), ("planTier", ASCENDING), ("templateCategory", ASCENDING)]
    )
    db.invitation_template_snapshots.create_index([("sourceId", ASCENDING)])
    db.invitation_template_snapshots.create_index([("sourceId", ASCENDING), ("version", ASCENDING)], unique=True)
    db.invitation_template_snapshots.create_index([("slug", ASCENDING)])
    db.website_template_snapshots.create_index([("sourceId", ASCENDING)])
    db.website_template_snapshots.create_index([("sourceId", ASCENDING), ("version", ASCENDING)], unique=True)
    db.website_template_snapshots.create_index([("slug", ASCENDING)])
    db.customer_invitation_snapshots.create_index([("sourceId", ASCENDING)])
    db.customer_invitation_snapshots.create_index([("sourceId", ASCENDING), ("version", ASCENDING)], unique=True)
    db.customer_invitation_snapshots.create_index([("slug", ASCENDING)])
    db.customer_website_snapshots.create_index([("sourceId", ASCENDING)])
    db.customer_website_snapshots.create_index([("sourceId", ASCENDING), ("version", ASCENDING)], unique=True)
    db.customer_website_snapshots.create_index([("slug", ASCENDING)])
    db.payments.create_index([("id", ASCENDING)], unique=True)
    db.payments.create_index([("projectType", ASCENDING), ("projectId", ASCENDING)])
    db.payments.create_index([("provider", ASCENDING), ("status", ASCENDING)])
    db.payments.create_index([("createdAt", ASCENDING)])
    db.payment_receipt_emails.create_index([("id", ASCENDING)], unique=True)
    db.support_tickets.create_index([("id", ASCENDING)], unique=True)
    db.support_tickets.create_index([("reference", ASCENDING)], unique=True)
    db.support_tickets.create_index([("createdAt", ASCENDING)])
    db.support_tickets.create_index([("status", ASCENDING), ("category", ASCENDING)])
    db.discount_codes.create_index([("id", ASCENDING)], unique=True)
    db.discount_codes.create_index([("codeNormalized", ASCENDING)], unique=True)
    db.discount_codes.create_index([("active", ASCENDING), ("createdAt", ASCENDING)])
    db.media_assets.create_index([("id", ASCENDING)], unique=True)
    db.media_assets.create_index([("scope", ASCENDING)])
    db.media_assets.create_index([("ownerId", ASCENDING)])
    db.media_assets.create_index([("createdAt", ASCENDING)])
    db.pricing_plans.create_index([("id", ASCENDING)], unique=True)
    db.pricing_plans.create_index([("code", ASCENDING)], unique=True)
    db.pricing_plans.create_index([("productType", ASCENDING), ("active", ASCENDING)])
    db.pricing_plans.create_index([("productType", ASCENDING), ("sortOrder", ASCENDING)])
    db.pricing_components.create_index([("id", ASCENDING)], unique=True)
    db.pricing_components.create_index([("productType", ASCENDING), ("componentCode", ASCENDING)], unique=True)
    db.pricing_components.create_index([("productType", ASCENDING), ("active", ASCENDING)])
    db.pricing_components.create_index([("productType", ASCENDING), ("sortOrder", ASCENDING)])
    db.template_categories.create_index([("id", ASCENDING)], unique=True)
    db.template_categories.create_index([("productType", ASCENDING), ("categoryCode", ASCENDING)], unique=True)
    db.template_categories.create_index([("productType", ASCENDING), ("active", ASCENDING), ("sortOrder", ASCENDING)])


def ping_database() -> bool:
    get_client().admin.command("ping")
    return True


def close_database() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
