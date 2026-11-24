"""Operational evidence. Existing data is read-only; fixtures require a new isolated DB."""

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from time import perf_counter

import requests
from pymongo import MongoClient

from app.core.errors import NuvlyError
from app.modules.domain.product_listing import customer_product_page_pipeline
from app.modules.domain.repository import DomainRepository

VALIDATION_DATABASE = re.compile(r"^nuvly_validation_[a-z0-9_]{8,60}$")


def validate_isolated_target(settings, database_name):
    if settings.app_env not in {"development", "test", "staging", "uat"}:
        raise ValueError("VALIDATION_ENVIRONMENT_REQUIRED")
    if settings.payments_environment != "integration" or settings.payments_production_enabled:
        raise ValueError("INTEGRATION_PAYMENTS_REQUIRED")
    if not VALIDATION_DATABASE.fullmatch(database_name) or database_name == settings.mongodb_db_name:
        raise ValueError("ISOLATED_DATABASE_REQUIRED")


def connect(settings):
    # Exception strings may contain connection details; report only their class.
    logging.getLogger("pymongo").setLevel(logging.CRITICAL)
    return MongoClient(
        settings.mongodb_uri,
        tls=True,
        tlsAllowInvalidCertificates=False,
        tlsAllowInvalidHostnames=False,
        serverSelectionTimeoutMS=8000,
        connectTimeoutMS=8000,
        socketTimeoutMS=8000,
        appname="nuvly-operational-validation",
    )


def check_http(url):
    if not url:
        return {"status": "blocked", "code": "URL_NOT_CONFIGURED"}
    started = perf_counter()
    try:
        with requests.Session() as session:
            response = session.get(url, timeout=8, allow_redirects=False)
            result = {
                "status": "passed" if response.status_code == 200 else "failed",
                "httpStatus": response.status_code,
                "https": url.startswith("https://"),
                "durationMs": round((perf_counter() - started) * 1000),
            }
            if response.headers.get("content-type", "").startswith("application/json"):
                payload = response.json()
                if isinstance(payload, dict):
                    # Never retain health exception text or arbitrary response content.
                    result["ready"] = payload.get("status") == "ready" and payload.get("database") == "ok"
                    if not result["ready"]:
                        result["status"] = "failed"
            return result
    except Exception as error:
        return {"status": "blocked", "errorType": type(error).__name__}


def summarize_explain(explain):
    indexes = set()
    examined = []

    def collect_indexes(node):
        if isinstance(node, dict):
            if isinstance(node.get("indexName"), str):
                indexes.add(node["indexName"])
            for value in node.values():
                collect_indexes(value)
        elif isinstance(node, list):
            for value in node:
                collect_indexes(value)

    def visit(node):
        if isinstance(node, dict):
            if "winningPlan" in node:
                collect_indexes(node["winningPlan"])
            if isinstance(node.get("totalDocsExamined"), int):
                examined.append(node["totalDocsExamined"])
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(explain)
    return {
        "status": "passed" if explain.get("ok") and "ownerId_1_updatedAt_-1_id_1" in indexes else "failed",
        "winningIndexes": sorted(indexes),
        "documentsExamined": max(examined) if examined else None,
    }


def read_only_report(settings, client=None):
    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "mode": "read-only",
        "environment": settings.app_env,
        "checks": {
            "stagingIdentity": {
                "status": "passed" if settings.app_env in {"staging", "uat"} else "blocked",
                "code": "DECLARED_ENVIRONMENT_ONLY",
            },
            "integrationPayments": {
                "status": "passed"
                if settings.payments_environment == "integration" and not settings.payments_production_enabled
                else "failed"
            },
            "httpsOrigins": {
                "status": "passed"
                if all(
                    (url or "").startswith("https://")
                    for url in (settings.public_base_url, settings.frontend_public_base_url)
                )
                else "blocked",
                "code": "HTTPS_REQUIRED_FOR_STAGING_COOKIES",
            },
            "durableMediaDeclared": {
                "status": "unverified" if settings.media_storage_durable else "blocked",
                "code": "RESTART_AND_RESTORE_EVIDENCE_REQUIRED",
            },
        },
        "remaining": [
            "browser_sessions",
            "payment_uat",
            "instance_replacement",
            "backup_restore",
            "real_network_timeout",
            "snapshot_reconciliation",
            "published_editor_roundtrip",
        ],
        "phaseComplete": False,
    }
    checks = report["checks"]
    started = perf_counter()
    owned_client = client is None
    try:
        if client is None:
            client = connect(settings)
        client.admin.command("ping")
        checks["mongoTls"] = {"status": "passed", "durationMs": round((perf_counter() - started) * 1000)}
        try:
            indexes = client[settings.mongodb_db_name].customer_websites.index_information()
            expected = [("ownerId", 1), ("updatedAt", -1), ("id", 1)]
            checks["customerProductIndex"] = {
                "status": "passed"
                if any(list(index.get("key", [])) == expected for index in indexes.values())
                else "failed"
            }
        except Exception as error:
            checks["customerProductIndex"] = {"status": "blocked", "errorType": type(error).__name__}
    except Exception as error:
        checks["mongoTls"] = {"status": "blocked", "errorType": type(error).__name__}
    finally:
        if owned_client and client is not None:
            client.close()
    backend = (settings.public_base_url or "").rstrip("/")
    checks["apiHealth"] = check_http(backend + settings.api_prefix + "/health") if backend else check_http(None)
    checks["frontend"] = check_http(settings.frontend_public_base_url)
    return report


class ValidationRepository(DomainRepository):
    def __init__(self, database):
        self.database = database

    def collection(self, collection_name):
        return self.database[collection_name]


def exercise_isolated_database(settings, client, database_name):
    """Use real Mongo operations against a previously absent disposable database.

    No existing database or collection is cleared, overwritten or dropped. Fixtures
    are retained for inspection; removal is a separate operator action.
    """
    validate_isolated_target(settings, database_name)
    if database_name in client.list_database_names():
        raise ValueError("VALIDATION_DATABASE_ALREADY_EXISTS")
    db = client[database_name]
    db.create_collection("validation_control")
    collection = db.customer_websites
    collection.create_index([("id", 1)], unique=True)
    collection.create_index([("ownerId", 1), ("updatedAt", -1), ("id", 1)])
    now = datetime.now(timezone.utc).isoformat()
    documents = [
        {
            "id": f"fixture_{index:04}",
            "ownerId": "validation_owner" if index < 240 else "other_owner",
            "updatedAt": now,
            "createdAt": now,
            "customerStatus": "published",
            "templateId": "validation_template",
            "title": "Synthetic validation project",
            "payment": {"status": "paid"},
            "content": {"private": "MUST_NOT_APPEAR_IN_CARDS"},
        }
        for index in range(300)
    ]
    collection.insert_many(documents)
    pipeline = customer_product_page_pipeline("validation_owner", 10, 20)
    started = perf_counter()
    page = next(iter(collection.aggregate(pipeline, maxTimeMS=10000)), {})
    items = page.get("items", [])
    total = (page.get("count") or [{}])[0].get("total", 0)
    pagination_ok = (
        total == 240
        and [item["id"] for item in items] == [f"fixture_{index:04}" for index in range(20, 30)]
        and all("content" not in item and item.get("ownerId") == "validation_owner" for item in items)
    )
    pagination_ms = round((perf_counter() - started) * 1000)
    explain = db.command(
        "explain", {"aggregate": "customer_websites", "pipeline": pipeline, "cursor": {}}, verbosity="executionStats"
    )
    collection.insert_one({"id": "cas_fixture", "updatedAt": now, "ownerId": "validation_cas"})
    repository = ValidationRepository(db)

    def save(index):
        try:
            repository.replace_document(
                "customer_websites",
                "cas_fixture",
                {
                    "id": "cas_fixture",
                    "updatedAt": (datetime.fromisoformat(now) + timedelta(microseconds=index + 1)).isoformat(),
                    "ownerId": "validation_cas",
                },
                "Missing fixture",
                "FIXTURE_NOT_FOUND",
                "DUPLICATE_FIXTURE",
                expected_updated_at=now,
            )
            return "saved"
        except NuvlyError as error:
            if error.status_code != 409:
                raise
            return "conflict"

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(save, range(8)))
    reconciled = collection.find_one({"id": "cas_fixture"}, {"_id": 0, "updatedAt": 1})
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "mode": "isolated-database",
        "database": database_name,
        "fixturesRetained": True,
        "checks": {
            "pagination": {
                "status": "passed" if pagination_ok else "failed",
                "durationMs": pagination_ms,
                "fixtures": 300,
            },
            "explain": summarize_explain(explain),
            "concurrentCas": {
                "status": "passed" if outcomes.count("saved") == 1 and outcomes.count("conflict") == 7 else "failed"
            },
            "readAfterWrite": {"status": "passed" if reconciled and reconciled["updatedAt"] != now else "failed"},
        },
        "phaseComplete": False,
    }
