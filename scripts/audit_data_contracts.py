"""Read-only data audit. Prints identifiers/field codes, never customer content."""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import close_database, get_database
from app.core.errors import NuvlyError
from app.core.value_types import clp_amount, iso_timestamp
from app.modules.domain.normalizer import normalize_document

COLLECTIONS = (
    "invitation_templates",
    "website_templates",
    "customer_invitations",
    "customer_websites",
    "pricing_plans",
    "pricing_components",
    "payments",
    "discount_codes",
)
MONEY_FIELDS = {
    "basePrice",
    "basePriceMonthly",
    "basePriceYearly",
    "extraPrice",
    "amount",
    "subtotalAmount",
    "discountAmount",
    "customDomainSurcharge",
    "extrasTotal",
    "initialAmount",
    "renewalAmount",
}
TIMESTAMP_FIELDS = {"createdAt", "updatedAt", "selectedAt", "paidAt", "lastPublishedAt", "expiresAt", "changedAt"}


def audit_document(collection, document):
    issues = []

    def visit(value, path=""):
        if isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]")
        elif isinstance(value, dict):
            for key, child in value.items():
                field = f"{path}.{key}" if path else key
                if child is not None and key in MONEY_FIELDS:
                    try:
                        clp_amount(child)
                    except ValueError:
                        issues.append({"field": field, "code": "INVALID_CLP_AMOUNT"})
                if child is not None and key in TIMESTAMP_FIELDS:
                    try:
                        if not isinstance(child, str):
                            raise ValueError("Not an ISO string")
                        iso_timestamp(child)
                    except ValueError:
                        issues.append({"field": field, "code": "INVALID_TIMESTAMP"})
                visit(child, field)

    # Inspect structural fields only. Editorial text/config can use arbitrary
    # names (e.g. a hero prop named amount) and must not be interpreted as money.
    structural = {
        key: document[key]
        for key in (
            *MONEY_FIELDS,
            *TIMESTAMP_FIELDS,
            "metadata",
            "payment",
            "billingTerms",
            "variants",
            "statusHistory",
        )
        if key in document
    }
    if isinstance(structural.get("metadata"), dict):
        structural["metadata"] = {k: v for k, v in structural["metadata"].items() if k in MONEY_FIELDS}
    visit(structural)
    if collection in COLLECTIONS[:4]:
        status_field = "customerStatus" if collection.startswith("customer_") else "templateStatus"
        try:
            normalize_document(document, status_field)
        except NuvlyError as error:
            issues.append({"field": "document", "code": error.code})
        except ValueError, TypeError, KeyError:
            issues.append({"field": "document", "code": "INVALID_DOCUMENT_SHAPE"})
    return issues


def run(db, *, summary_only=False):
    checked = invalid = 0
    issues_by_code = Counter()
    collections = {}
    for name in COLLECTIONS:
        collections[name] = {"checked": 0, "invalid": 0}
        for document in db[name].find({}, {"_id": 0}):
            checked += 1
            collections[name]["checked"] += 1
            issues = audit_document(name, document)
            if issues:
                invalid += 1
                collections[name]["invalid"] += 1
                issues_by_code.update(issue["code"] for issue in issues)
                if not summary_only:
                    print(json.dumps({"collection": name, "id": document.get("id"), "issues": issues}))
    summary = {"checked": checked, "invalid": invalid, "readOnly": True}
    if summary_only:
        summary.update(collections=collections, issuesByCode=dict(issues_by_code))
    print(json.dumps(summary))
    return 1 if invalid else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", action="store_true", help="Aggregate results without document identifiers")
    args = parser.parse_args()
    try:
        result = run(get_database(), summary_only=args.summary)
    finally:
        close_database()
    raise SystemExit(result)
