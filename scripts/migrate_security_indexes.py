"""Run explicitly before deployment, during a write maintenance window.

Only replaces known legacy indexes whose definitions differ. Never runs at startup.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import close_database, create_indexes, get_database


def migrate(db) -> list[str]:
    replacements = []
    definitions = [
        ("customer_invitations", "slug_1", [("slug", 1)], False, None),
        ("customer_websites", "slug_1", [("slug", 1)], False, None),
        ("customer_invitations", "publicSlug_1", [("publicSlug", 1)], True, {"publicSlug": {"$type": "string"}}),
        ("customer_websites", "publicSlug_1", [("publicSlug", 1)], True, {"publicSlug": {"$type": "string"}}),
    ]
    for collection_name, name, keys, unique, partial in definitions:
        collection = db[collection_name]
        existing = collection.index_information().get(name)
        if existing and (
            list(existing["key"]) != keys
            or bool(existing.get("unique")) != unique
            or existing.get("partialFilterExpression") != partial
        ):
            collection.drop_index(name)
            replacements.append(f"{collection_name}.{name}")
        options = {"unique": unique}
        if partial is not None:
            options["partialFilterExpression"] = partial
        collection.create_index(keys, **options)
    components = db["pricing_components"]
    components.create_index([("productType", 1), ("componentCode", 1)], unique=True)
    if "componentCode_1" in components.index_information():
        components.drop_index("componentCode_1")
        replacements.append("pricing_components.componentCode_1")
    return replacements


if __name__ == "__main__":
    try:
        replaced = migrate(get_database())
        create_indexes()
        print(f"Index migration complete: {len(replaced)} legacy indexes replaced.")
    finally:
        close_database()
