import json
from copy import deepcopy

import pytest
from test_payments_flow import (
    InMemoryDomainRepository,
    _create_customer_invitation_project,
    _create_customer_project,
)

from app.modules.domain.schemas import SnapshotResponse
from app.modules.domain.services import (
    CUSTOMER_INVITATION_CONFIG,
    CUSTOMER_WEBSITE_CONFIG,
    CustomerProjectService,
)


@pytest.mark.parametrize(
    "config,create",
    [
        (CUSTOMER_WEBSITE_CONFIG, _create_customer_project),
        (CUSTOMER_INVITATION_CONFIG, _create_customer_invitation_project),
    ],
)
def test_public_projection_protects_old_and_new_snapshots_without_mutating_private_version(config, create):
    repo = InMemoryDomainRepository()
    project = create(repo)
    project.update(
        ownerId="owner",
        ownerEmail="owner@example.test",
        formSubmissions=[{"private": "PRIVATE_CANARY"}],
        guests=[{"private": "PRIVATE_CANARY"}],
        rsvpResponses=[{"private": "PRIVATE_CANARY"}],
    )
    project["payment"] = {"status": "paid", "testMode": True}
    repo.replace_document(config.collection, project["id"], project, "missing", "missing", "duplicate")
    service = CustomerProjectService(config, repository=repo)
    publication = service.publish_for_owner(project["id"], owner_id="owner")
    # Simulate legacy snapshots with unknown private root and nested fields.
    stored = repo.collections[config.snapshot_collection][0]
    stored["snapshot"]["unknownPrivateField"] = "PRIVATE_CANARY"
    stored["snapshot"]["metadata"]["privateNote"] = "PRIVATE_CANARY"
    stored["snapshot"]["blocks"][0]["props"]["customerData"] = {"secret": "PRIVATE_CANARY"}
    before = deepcopy(stored)
    public = SnapshotResponse.model_validate(service.get_published_by_slug(project["publicSlug"])).model_dump()
    assert "PRIVATE_CANARY" not in json.dumps(public)
    assert public["snapshot"]["title"] == project["title"]
    assert public["snapshot"]["blocks"][0]["id"] == project["blocks"][0]["id"]
    assert repo.collections[config.snapshot_collection][0] == before
    assert publication["snapshot"]["ownerId"] == "owner"
    assert service.get_for_owner(project["id"], owner_id="owner")["ownerEmail"] == "owner@example.test"
