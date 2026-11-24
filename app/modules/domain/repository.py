import logging
from typing import Any, Dict, List, Optional

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.core.database import get_database
from app.core.errors import NuvlyError

logger = logging.getLogger(__name__)


class DomainRepository:
    def customer_product_page(self, collection_name, owner_id, limit, skip):
        from app.modules.domain.product_listing import customer_product_page_pipeline

        if collection_name not in {"customer_websites", "customer_invitations"}:
            raise ValueError("Unsupported customer collection")
        if not owner_id:
            return {"items": [], "total": 0}
        pipeline = customer_product_page_pipeline(owner_id, limit, skip)
        result = next(
            iter(self.collection(collection_name).aggregate(pipeline, allowDiskUse=True, maxTimeMS=10000)), {}
        )
        counts = result.get("count", [])
        return {"items": result.get("items", []), "total": counts[0]["total"] if counts else 0}

    def claim_customer_project(self, collection_name, project_id, old_email, owner_id, email):
        result = self.collection(collection_name).find_one_and_update(
            {"id": project_id, "ownerId": None, "ownerEmail": old_email},
            {"$set": {"ownerId": owner_id, "ownerEmail": email}},
            projection={"_id": 0},
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            raise NuvlyError(
                "El proyecto ya fue vinculado. Actualiza e intenta nuevamente.", 409, "PROJECT_CLAIM_CONFLICT"
            )
        return self._public_document(result)

    def list_admin_customer_websites(self, search, limit, skip):
        import re

        filters = (
            {
                "$or": [
                    {field: {"$regex": re.escape(search), "$options": "i"}}
                    for field in ("id", "title", "ownerEmail", "customerData.name")
                ]
            }
            if search
            else {}
        )
        fields = {
            key: 1
            for key in ("id", "title", "ownerEmail", "customerStatus", "publicSlug", "publishedSnapshotId", "updatedAt")
        }
        fields["_id"] = 0
        collection = self.collection("customer_websites")
        return {
            "items": list(collection.find(filters, fields).sort("updatedAt", -1).skip(skip).limit(limit)),
            "total": collection.count_documents(filters),
        }

    def restore_customer_website(self, project_id, expected_snapshot_id, changes, event, *, expected_updated_at=None):
        filters = {
            "id": project_id,
            "publishedSnapshotId": expected_snapshot_id,
            "customerStatus": "published",
            "payment.status": "paid",
        }
        if expected_updated_at is not None:
            filters["updatedAt"] = expected_updated_at
        result = self.collection("customer_websites").find_one_and_update(
            filters,
            {"$set": changes, "$push": {"statusHistory": event}},
            projection={"_id": 0},
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            raise NuvlyError(
                "La web cambió mientras revisabas las versiones. Actualiza el historial y vuelve a revisarlo.",
                409,
                "WEBSITE_VERSION_CONFLICT",
            )
        return self._public_document(result)

    def discard_unpublished_restore_snapshot(self, snapshot_id):
        self.collection("customer_website_snapshots").delete_one({"id": snapshot_id, "restoration": {"$exists": True}})

    def iter_operating_costs(self, environment):
        return self.collection("operating_costs").find({"environment": environment}, {"_id": 0, "history": 0})

    def system_overview_counts(self):
        return {
            "publishedWebsites": self.collection("customer_websites").count_documents({"customerStatus": "published"}),
            "publishedInvitations": self.collection("customer_invitations").count_documents(
                {"customerStatus": "published"}
            ),
            "drafts": sum(
                self.collection(name).count_documents({"customerStatus": "draft"})
                for name in ("customer_websites", "customer_invitations")
            ),
            "openSupport": self.collection("support_tickets").count_documents(
                {"status": {"$in": ["open", "in_progress"]}}
            ),
            "waitingCustomer": self.collection("support_tickets").count_documents({"status": "waiting_customer"}),
        }

    def iter_reporting_project_templates(self):
        for collection in ("customer_websites", "customer_invitations"):
            yield from self.collection(collection).find({}, {"_id": 0, "id": 1, "templateId": 1})

    def iter_analytics_events(self, since, until, environment):
        return (
            self.collection("analytics_events")
            .find(
                {"receivedAt": {"$gte": since.isoformat(), "$lt": until.isoformat()}, "environment": environment},
                {"_id": 0},
            )
            .sort([("sessionId", 1), ("sequence", 1), ("receivedAt", 1)])
        )

    def reporting_templates(self):
        return {
            item["id"]: item.get("title") or item["id"]
            for collection in ("website_templates", "invitation_templates")
            for item in self.collection(collection).find({}, {"_id": 0, "id": 1, "title": 1})
        }

    def iter_reporting_projects(self):
        payment_fields = {
            key: 1
            for key in (
                "id",
                "projectId",
                "environment",
                "testMode",
                "status",
                "amount",
                "currency",
                "createdAt",
                "updatedAt",
                "paidAt",
                "billingTerms",
            )
        }
        payment_fields["_id"] = 0
        for collection, snapshots, kind in (
            ("customer_websites", "customer_website_snapshots", "website"),
            ("customer_invitations", "customer_invitation_snapshots", "invitation"),
        ):
            fields = {
                key: 1
                for key in (
                    "id",
                    "title",
                    "templateId",
                    "ownerEmail",
                    "customerStatus",
                    "createdAt",
                    "updatedAt",
                    "firstPublishedAt",
                    "subscription",
                    "payments",
                    "firstSnapshot",
                )
            }
            fields["_id"] = 0
            for project in self.collection(collection).aggregate(
                [
                    {
                        "$lookup": {
                            "from": "payments",
                            "localField": "id",
                            "foreignField": "projectId",
                            "pipeline": [{"$project": payment_fields}],
                            "as": "payments",
                        }
                    },
                    {
                        "$lookup": {
                            "from": snapshots,
                            "localField": "id",
                            "foreignField": "sourceId",
                            "pipeline": [
                                {"$sort": {"publishedAt": 1}},
                                {"$limit": 1},
                                {"$project": {"_id": 0, "publishedAt": 1}},
                            ],
                            "as": "firstSnapshot",
                        }
                    },
                    {"$project": fields},
                ]
            ):
                project["projectType"] = kind
                yield project

    def iter_commercial_payments(self, since, until):
        def date_value(field):
            return {"$convert": {"input": field, "to": "date", "onError": None, "onNull": None}}

        fields = {
            key: 1
            for key in (
                "id",
                "projectId",
                "projectTitle",
                "projectType",
                "ownerId",
                "ownerEmail",
                "provider",
                "status",
                "amount",
                "currency",
                "createdAt",
                "updatedAt",
                "paidAt",
                "templateId",
                "refundedAt",
                "refundedAmount",
                "refundAmount",
                "environment",
                "testMode",
                "planTier",
            )
        }
        fields["_id"] = 0
        fields["receiptEmailStatus"] = {"$arrayElemAt": ["$receipt.status", 0]}
        return self.collection("payments").aggregate(
            [
                {
                    "$addFields": {
                        "reportCreated": date_value("$createdAt"),
                        "reportPaid": date_value({"$ifNull": ["$paidAt", {"$ifNull": ["$updatedAt", "$createdAt"]}]}),
                        "reportRefunded": date_value({"$ifNull": ["$refundedAt", "$updatedAt"]}),
                    }
                },
                {
                    "$match": {
                        "$or": [
                            {key: {"$gte": since, "$lt": until}}
                            for key in ("reportCreated", "reportPaid", "reportRefunded")
                        ]
                    }
                },
                {"$sort": {"reportCreated": -1, "id": 1}},
                {
                    "$lookup": {
                        "from": "payment_receipt_emails",
                        "localField": "id",
                        "foreignField": "id",
                        "as": "receipt",
                    }
                },
                {"$project": fields},
            ],
            allowDiskUse=True,
        )

    def iter_support_tickets(self, since, until):
        return (
            self.collection("support_tickets")
            .find(
                {"createdAt": {"$gte": since.isoformat(), "$lt": until.isoformat()}},
                {"_id": 0, "message": 0, "replies": 0, "events": 0},
            )
            .sort([("createdAt", -1), ("id", 1)])
        )

    def patch_support_ticket(self, ticket_id, updates, event=None, reply=None):
        operation = {"$set": updates}
        pushes = {}
        if event:
            pushes["events"] = event
        if reply:
            pushes["replies"] = reply
        if pushes:
            operation["$push"] = pushes
        document = self.collection("support_tickets").find_one_and_update(
            {"id": ticket_id}, operation, return_document=ReturnDocument.AFTER
        )
        if not document:
            raise NuvlyError("No encontramos ese caso.", 404, "SUPPORT_TICKET_NOT_FOUND")
        return self._public_document(document)

    def finish_support_reply(self, ticket_id, reply_id, status, now):
        updates = {
            "updatedAt": now,
            "replies.$.deliveryStatus": status,
            "replies.$.sentAt": now if status == "sent" else None,
        }
        operation = {"$set": updates}
        if status == "sent":
            updates.update(status="waiting_customer", resolvedAt=None)
            operation["$min"] = {"firstReplyAt": now}
        return self._public_document(
            self.collection("support_tickets").find_one_and_update(
                {"id": ticket_id, "replies.id": reply_id}, operation, return_document=ReturnDocument.AFTER
            )
        )

    def enqueue_payment_email(self, document):
        # The payment ID is also Mongo's unique _id: callbacks cannot enqueue twice.
        try:
            self.collection("payment_receipt_emails").update_one(
                {"_id": document["id"]},
                {"$setOnInsert": document},
                upsert=True,
            )
        except DuplicateKeyError:
            pass
        return self.find_document("payment_receipt_emails", {"id": document["id"]})

    def claim_payment_email(self, payment_id, now, lease_id, lease_until):
        return self._public_document(
            self.collection("payment_receipt_emails").find_one_and_update(
                {
                    "_id": payment_id,
                    "$or": [
                        {"status": {"$in": ["pending", "failed", "unavailable"]}, "nextAttemptAt": {"$lte": now}},
                        {"status": "sending", "leaseUntil": {"$lte": now}},
                    ],
                },
                {
                    "$set": {"status": "sending", "leaseId": lease_id, "leaseUntil": lease_until, "lastAttemptAt": now},
                    "$inc": {"attempts": 1},
                },
                return_document=ReturnDocument.AFTER,
            )
        )

    def finish_payment_email(self, payment_id, lease_id, updates):
        self.collection("payment_receipt_emails").update_one(
            {"_id": payment_id, "leaseId": lease_id, "status": "sending"},
            {"$set": updates},
        )
        return self.find_document("payment_receipt_emails", {"id": payment_id})

    @staticmethod
    def _public_document(document: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if document is None:
            return None
        sanitized = dict(document)
        sanitized.pop("_id", None)
        return sanitized

    def collection(self, collection_name: str):
        return get_database()[collection_name]

    def database_name(self) -> str:
        return get_database().name

    @staticmethod
    def _duplicate_key_context(exc: DuplicateKeyError) -> Dict[str, Any]:
        details = exc.details or {}
        key_pattern = details.get("keyPattern") or {}
        key_value = details.get("keyValue") or {}
        index_name = details.get("indexName") or details.get("index")
        return {
            "details": details,
            "index_name": index_name,
            "key_pattern": key_pattern,
            "key_value": key_value,
            "is_slug_duplicate": "slug" in key_pattern or "slug" in key_value,
            "is_snapshot_version_duplicate": "sourceId" in key_pattern and "version" in key_pattern,
            "is_code_duplicate": "codeNormalized" in key_pattern
            or "codeNormalized" in key_value
            or "code" in key_pattern
            or "code" in key_value,
        }

    def insert_document(
        self,
        collection_name: str,
        document: Dict[str, Any],
        duplicate_message: str,
        duplicate_code: str = "DUPLICATED_SLUG",
    ) -> Dict[str, Any]:
        try:
            self.collection(collection_name).insert_one(document)
        except DuplicateKeyError as exc:
            context = self._duplicate_key_context(exc)
            logger.warning(
                "Duplicate key on insert | database=%s collection=%s slug=%s id=%s indexName=%s keyPattern=%s keyValue=%s details=%s",
                self.database_name(),
                collection_name,
                document.get("slug"),
                document.get("id"),
                context["index_name"],
                context["key_pattern"],
                context["key_value"],
                context["details"],
            )
            if context["is_slug_duplicate"] or context["is_code_duplicate"] or context["is_snapshot_version_duplicate"]:
                raise NuvlyError(duplicate_message, 409, duplicate_code)
            raise NuvlyError(
                f"Mongo duplicate key conflict in {collection_name}. Check logs for index details.",
                500,
                "MONGO_DUPLICATE_KEY",
            )
        return self._public_document(document)

    def find_documents(
        self,
        collection_name: str,
        filters: Dict[str, Any],
        limit: int = 20,
        skip: int = 0,
        sort_field: str = "updatedAt",
        sort_direction: int = -1,
    ) -> List[Dict[str, Any]]:
        cursor = self.collection(collection_name).find(filters, {"_id": 0}).sort(sort_field, sort_direction).skip(skip)
        if limit > 0:
            cursor = cursor.limit(limit)
        return [self._public_document(document) for document in cursor]

    def archive_temporary_draft(self, collection_name, document, reason):
        from app.core.utils import utc_now_iso

        # Recheck payment/publication state atomically: a concurrent checkout must win.
        self.collection(collection_name).update_one(
            {
                "id": document["id"],
                "updatedAt": document.get("updatedAt"),
                "customerStatus": "draft",
                "payment.status": "unpaid",
                "payment.paidAt": None,
                "payment.providerPaymentId": None,
                "publishedSnapshotId": None,
                "lastPublishedAt": None,
            },
            {"$set": {"draftArchivedAt": utc_now_iso(), "draftArchiveReason": reason}},
        )

    def find_document(self, collection_name: str, filters: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self._public_document(self.collection(collection_name).find_one(filters, {"_id": 0}))

    def find_document_by_slug(self, collection_name: str, slug: str) -> Optional[Dict[str, Any]]:
        filters = {"slug": slug}
        document = self.find_document(collection_name, filters)
        logger.info(
            "Slug lookup | database=%s collection=%s slug=%s found=%s foundId=%s",
            self.database_name(),
            collection_name,
            slug,
            document is not None,
            document.get("id") if document else None,
        )
        return document

    def replace_document(
        self,
        collection_name: str,
        document_id: str,
        document: Dict[str, Any],
        not_found_message: str,
        not_found_code: str,
        duplicate_message: str,
        duplicate_code: str = "DUPLICATED_SLUG",
        expected_updated_at: str | None = None,
    ) -> Dict[str, Any]:
        filters = {"id": document_id}
        if expected_updated_at is not None:
            filters["updatedAt"] = expected_updated_at
        try:
            result = self.collection(collection_name).replace_one(filters, document)
        except DuplicateKeyError as exc:
            context = self._duplicate_key_context(exc)
            logger.warning(
                "Duplicate key on replace | database=%s collection=%s slug=%s id=%s indexName=%s keyPattern=%s keyValue=%s details=%s",
                self.database_name(),
                collection_name,
                document.get("slug"),
                document_id,
                context["index_name"],
                context["key_pattern"],
                context["key_value"],
                context["details"],
            )
            if context["is_slug_duplicate"] or context["is_code_duplicate"]:
                raise NuvlyError(duplicate_message, 409, duplicate_code)
            raise NuvlyError(
                f"Mongo duplicate key conflict in {collection_name}. Check logs for index details.",
                500,
                "MONGO_DUPLICATE_KEY",
            )
        if result.matched_count == 0:
            if expected_updated_at is not None:
                raise NuvlyError(
                    "El proyecto cambió en otra sesión. Recarga antes de guardar.", 409, "PROJECT_VERSION_CONFLICT"
                )
            raise NuvlyError(not_found_message, 404, not_found_code)
        return self._public_document(document)

    def discard_unpublished_snapshot(self, collection_name, snapshot_id):
        self.collection(collection_name).delete_one({"id": snapshot_id})

    def count_documents(self, collection_name: str, filters: Dict[str, Any]) -> int:
        return self.collection(collection_name).count_documents(filters)

    def update_document_fields(
        self,
        collection_name: str,
        document_id: str,
        updates: Dict[str, Any],
        not_found_message: str,
        not_found_code: str,
    ) -> Dict[str, Any]:
        result = self.collection(collection_name).find_one_and_update(
            {"id": document_id},
            {"$set": updates},
            projection={"_id": 0},
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            raise NuvlyError(not_found_message, 404, not_found_code)
        return self._public_document(result)
