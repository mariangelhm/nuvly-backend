from pymongo import ASCENDING, MongoClient
from pymongo.database import Database

from app.core.config import get_settings

_client: MongoClient | None = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=8000)
    return _client


def get_database() -> Database:
    settings = get_settings()
    return get_client()[settings.mongodb_db_name]


def create_indexes() -> None:
    db = get_database()
    db.experiences.create_index([("slug", ASCENDING), ("experienceType", ASCENDING)], unique=True)
    db.experiences.create_index([("status", ASCENDING)])
    db.experiences.create_index([("experienceType", ASCENDING)])
    db.experiences.create_index([("updatedAt", ASCENDING)])
    db.experience_snapshots.create_index([("experienceId", ASCENDING)])
    db.experience_snapshots.create_index([("experienceId", ASCENDING), ("version", ASCENDING)], unique=True)
    db.experience_snapshots.create_index([("experienceType", ASCENDING), ("slug", ASCENDING)])


def ping_database() -> bool:
    get_client().admin.command("ping")
    return True


def close_database() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
