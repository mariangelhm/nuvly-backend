"""Validate exported Studio presets through create/update without database writes."""

import argparse
import json
import logging
import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.modules.domain.schemas import (
    InvitationTemplateCreate,
    InvitationTemplateUpdate,
    WebsiteTemplateCreate,
    WebsiteTemplateUpdate,
)
from app.modules.domain.services import INVITATION_TEMPLATE_CONFIG, WEBSITE_TEMPLATE_CONFIG, TemplateService
from app.modules.pricing.service import ensure_pricing_seed

parser = argparse.ArgumentParser()
parser.add_argument("documents", type=Path)
parser.add_argument("--report", type=Path)
args = parser.parse_args()
logging.disable(logging.CRITICAL)
repository_type = runpy.run_path(str(Path(__file__).with_name("test_customer_project_creation.py")))[
    "InMemoryDomainRepository"
]
results = []
for entry in json.loads(args.documents.read_text(encoding="utf-8")):
    repository = repository_type()
    ensure_pricing_seed(repository=repository)
    document = entry["document"]
    web = document["experienceType"] == "web"
    service = TemplateService(WEBSITE_TEMPLATE_CONFIG if web else INVITATION_TEMPLATE_CONFIG, repository)
    try:
        created = service.create((WebsiteTemplateCreate if web else InvitationTemplateCreate).model_validate(document))
        service.update(
            created["id"], (WebsiteTemplateUpdate if web else InvitationTemplateUpdate).model_validate(document)
        )
        results.append({"presetId": entry["presetId"], "create": "passed", "update": "passed"})
    except Exception as error:
        results.append({"presetId": entry["presetId"], "error": str(error)})
report = {"presets": len(results), "passed": sum("error" not in result for result in results), "results": results}
if args.report:
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
print(
    json.dumps(
        {"presets": report["presets"], "passed": report["passed"], "failures": [r for r in results if "error" in r]},
        ensure_ascii=False,
        indent=2,
    )
)
assert report["passed"] == report["presets"]
