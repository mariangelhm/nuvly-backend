"""Bounded dashboard reads. Editor documents are fetched through their detail routes."""

from datetime import datetime, timedelta, timezone

CARD_FIELDS = (
    "id",
    "title",
    "productType",
    "planTier",
    "templateCategory",
    "customerStatus",
    "publicSlug",
    "ownerId",
    "templateId",
    "templateSnapshotId",
    "selectionSource",
    "selectedAt",
    "createdAt",
    "updatedAt",
    "lastPublishedAt",
    "publishedSnapshotId",
    "payment.status",
    "payment.paidAt",
    "payment.providerPaymentId",
    "payment.finalUrl",
    "payment.amount",
    "payment.currency",
    "payment.provider",
    "payment.environment",
    "payment.testMode",
    "metadata.basePrice",
    "metadata.monthlyMaintenancePrice",
    "metadata.yearlyMaintenancePrice",
    "metadata.coverImage",
    "metadata.previewImage",
    "metadata.previewVariant",
)


def customer_product_page_pipeline(owner_id, limit, skip, *, now=None):
    if not owner_id:
        raise ValueError("An owner ID is required")
    if not 1 <= limit <= 200 or skip < 0:
        raise ValueError("Invalid page bounds")
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=30)
    temporary = {
        "$and": [
            {"$eq": ["$customerStatus", "draft"]},
            {"$eq": [{"$ifNull": ["$payment.status", "unpaid"]}, "unpaid"]},
            *[
                {"$not": ["$" + key]}
                for key in (
                    "payment.paidAt",
                    "payment.providerPaymentId",
                    "publishedSnapshotId",
                    "lastPublishedAt",
                )
            ],
        ]
    }
    projection = {key: 1 for key in CARD_FIELDS}
    projection.update({"_id": 0, "draftArchivedAt": 1})
    return [
        {"$match": {"ownerId": owner_id}},
        {"$sort": {"updatedAt": -1, "id": 1}},
        {"$project": projection},
        {"$match": {"$expr": {"$not": ["$draftArchivedAt"]}}},
        {
            "$set": {
                "_temporary": temporary,
                "_touched": {
                    "$convert": {
                        "input": {"$cond": ["$updatedAt", "$updatedAt", "$createdAt"]},
                        "to": "date",
                        "onError": None,
                        "onNull": None,
                    }
                },
            }
        },
        {
            "$match": {
                "$expr": {
                    "$or": [
                        {"$not": ["$_temporary"]},
                        {"$eq": ["$_touched", None]},
                        {"$gte": ["$_touched", cutoff]},
                    ]
                }
            }
        },
        # Paid/published projects stay distinct; only temporary drafts share a template key.
        {
            "$group": {
                "_id": {
                    "$cond": [
                        {"$and": ["$_temporary", {"$ifNull": ["$templateId", False]}]},
                        {"kind": "temporary", "template": "$templateId"},
                        {"kind": "project", "id": "$id"},
                    ]
                },
                "document": {"$first": "$$ROOT"},
            }
        },
        {"$replaceRoot": {"newRoot": "$document"}},
        {
            "$facet": {
                "items": [
                    {"$sort": {"updatedAt": -1, "id": 1}},
                    {"$skip": skip},
                    {"$limit": limit},
                    {
                        "$unset": [
                            "_temporary",
                            "_touched",
                            "draftArchivedAt",
                            "publishedSnapshotId",
                            "payment.providerPaymentId",
                        ]
                    },
                ],
                "count": [{"$count": "total"}],
            }
        },
    ]
