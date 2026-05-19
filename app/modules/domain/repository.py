from typing import Any, Dict, List, Optional

from pymongo.errors import DuplicateKeyError

from app.core.database import get_database
from app.core.errors import NuvlyError


class DomainRepository:
    def collection(self, collection_name: str):
        return get_database()[collection_name]

    def insert_document(
        self,
        collection_name: str,
        document: Dict[str, Any],
        duplicate_message: str,
        duplicate_code: str = "DUPLICATED_SLUG",
    ) -> Dict[str, Any]:
        try:
            self.collection(collection_name).insert_one(document)
        except DuplicateKeyError:
            raise NuvlyError(duplicate_message, 409, duplicate_code)
        return document

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
        return list(cursor)

    def find_document(self, collection_name: str, filters: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self.collection(collection_name).find_one(filters, {"_id": 0})

    def replace_document(
        self,
        collection_name: str,
        document_id: str,
        document: Dict[str, Any],
        not_found_message: str,
        not_found_code: str,
        duplicate_message: str,
        duplicate_code: str = "DUPLICATED_SLUG",
    ) -> Dict[str, Any]:
        try:
            result = self.collection(collection_name).replace_one({"id": document_id}, document)
        except DuplicateKeyError:
            raise NuvlyError(duplicate_message, 409, duplicate_code)
        if result.matched_count == 0:
            raise NuvlyError(not_found_message, 404, not_found_code)
        return document

    def count_documents(self, collection_name: str, filters: Dict[str, Any]) -> int:
        return self.collection(collection_name).count_documents(filters)
