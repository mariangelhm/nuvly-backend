from pymongo import ASCENDING, MongoClient
from pymongo.database import Database
from pymongo.errors import OperationFailure

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
            tlsAllowInvalidCertificates=True,
            tlsAllowInvalidHostnames=True,
        )
    return _client


def get_database() -> Database:
    settings = get_settings()
    return get_client()[settings.mongodb_db_name]


def _drop_index_if_exists(collection, index_name: str) -> None:
    try:
        existing_indexes = collection.index_information()
        if index_name in existing_indexes:
            collection.drop_index(index_name)
    except OperationFailure:
        pass


def create_indexes() -> None:
    db = get_database()
    db.experiences.create_index([("slug", ASCENDING), ("experienceType", ASCENDING)], unique=True)
    db.experiences.create_index([("status", ASCENDING)])
    db.experiences.create_index([("experienceType", ASCENDING)])
    db.experiences.create_index([("updatedAt", ASCENDING)])
    db.experience_snapshots.create_index([("experienceId", ASCENDING)])
    db.experience_snapshots.create_index([("experienceId", ASCENDING), ("version", ASCENDING)], unique=True)
    db.experience_snapshots.create_index([("experienceType", ASCENDING), ("slug", ASCENDING)])
    db.invitation_templates.create_index([("slug", ASCENDING)], unique=True)
    db.invitation_templates.create_index([("templateStatus", ASCENDING)])
    db.invitation_templates.create_index([("updatedAt", ASCENDING)])
    db.invitation_templates.create_index([("metadata.catalogVisible", ASCENDING)])
    db.website_templates.create_index([("slug", ASCENDING)], unique=True)
    db.website_templates.create_index([("templateStatus", ASCENDING)])
    db.website_templates.create_index([("updatedAt", ASCENDING)])
    db.website_templates.create_index([("metadata.catalogVisible", ASCENDING)])
    _drop_index_if_exists(db.customer_invitations, "slug_1")
    _drop_index_if_exists(db.customer_websites, "slug_1")
    db.customer_invitations.create_index([("slug", ASCENDING)])
    db.customer_invitations.create_index([("customerStatus", ASCENDING)])
    db.customer_invitations.create_index([("updatedAt", ASCENDING)])
    db.customer_websites.create_index([("slug", ASCENDING)])
    db.customer_websites.create_index([("customerStatus", ASCENDING)])
    db.customer_websites.create_index([("updatedAt", ASCENDING)])
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
    db.media_assets.create_index([("id", ASCENDING)], unique=True)
    db.media_assets.create_index([("scope", ASCENDING)])
    db.media_assets.create_index([("ownerId", ASCENDING)])
    db.media_assets.create_index([("createdAt", ASCENDING)])


def ping_database() -> bool:
    get_client().admin.command("ping")
    return True


def close_database() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
