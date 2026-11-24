"""Measured navigation, checkout follow-up and contractual renewal dates."""

from calendar import monthrange
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from app.modules.domain.repository import DomainRepository
from app.modules.reporting.service import CHILE, money, parsed_time, payment_environment, resolve_report_environment

STAGES = [
    ("page_view", "Visita a Nuvly"),
    ("catalog_viewed", "Explora el catálogo"),
    ("template_viewed", "Ve una plantilla"),
    ("template_selected", "Elige personalizar"),
    ("editor_opened", "Abre el editor"),
    ("checkout_viewed", "Llega al resumen de pago"),
]


def add_months(value, months):
    year, month = divmod(value.year * 12 + value.month - 1 + months, 12)
    return value.replace(year=year, month=month + 1, day=min(value.day, monthrange(year, month + 1)[1]))


def behavior_report(events, payments, projects, templates, period, environment, now=None):
    now = now or datetime.now(timezone.utc)
    sessions, pages, actions = set(), Counter(), Counter()
    checkout_sessions = set()
    stages = [set() for _ in STAGES]
    progress = defaultdict(int)
    interest = defaultdict(lambda: {"views": set(), "selections": set()})
    for event in events:
        if not period.includes(parsed_time(event.get("receivedAt"))) or event.get("environment") != environment:
            continue
        sid, name = event["sessionId"], event["event"]
        sessions.add(sid)
        actions[name] += 1
        if name == "checkout_viewed":
            checkout_sessions.add(sid)
        if name == "page_view":
            pages[event.get("page") or "other"] += 1
        # Ordered, same-session funnel; revisits do not count twice.
        index = progress[sid]
        if index < len(STAGES) and name == STAGES[index][0]:
            stages[index].add(sid)
            progress[sid] += 1
        template = event.get("templateId")
        if template and name in ("template_viewed", "template_selected"):
            interest[template]["views" if name == "template_viewed" else "selections"].add(sid)
    project_list = list(projects)
    project_templates = {p["id"]: p.get("templateId") for p in project_list}
    best = defaultdict(lambda: {"count": 0, "amount": 0})
    approved = 0
    for payment in payments:
        if (
            payment_environment(payment) != environment
            or payment.get("status") not in ("paid", "refunded")
            or payment.get("currency", "CLP") != "CLP"
        ):
            continue
        if not period.includes(parsed_time(payment.get("paidAt") or payment.get("updatedAt"))):
            continue
        amount = money(payment.get("amount"))
        if amount is None:
            continue
        approved += 1
        template = payment.get("templateId") or project_templates.get(payment.get("projectId")) or "unknown"
        best[template]["count"] += 1
        best[template]["amount"] += float(amount)
    abandoned, drafts = [], 0
    for project in project_list:
        attempts = [p for p in project.get("payments", []) if payment_environment(p) == environment]
        # A later successful payment recovers all earlier attempts for this project,
        # including successes outside the report window.
        if any(p.get("status") in ("paid", "refunded") for p in attempts):
            continue
        if not attempts:
            if (
                not project.get("payments")
                and project.get("customerStatus") == "draft"
                and period.includes(parsed_time(project.get("updatedAt")))
            ):
                drafts += 1
            continue
        latest = max(attempts, key=lambda p: p.get("createdAt") or "")
        created = parsed_time(latest.get("createdAt"))
        if not period.includes(created) or latest.get("status") not in ("pending", "failed"):
            continue
        activity = max(
            filter(None, (created, parsed_time(latest.get("updatedAt")), parsed_time(project.get("updatedAt"))))
        )
        if activity > now - timedelta(hours=24):
            continue
        abandoned.append(
            {
                "projectId": project["id"],
                "title": project.get("title"),
                "email": project.get("ownerEmail"),
                "projectType": project["projectType"],
                "lastActivityAt": activity.isoformat(),
                "paymentStatus": latest["status"],
                "amount": float(money(latest.get("amount")) or 0),
            }
        )
    abandoned.sort(key=lambda p: p["lastActivityAt"], reverse=True)
    funnel = [
        {
            "key": name,
            "label": label,
            "sessions": len(stages[i]),
            "dropOff": len(stages[i]) - len(stages[i + 1]) if i + 1 < len(stages) else None,
        }
        for i, (name, label) in enumerate(STAGES)
    ]
    return {
        "period": period.as_dict(),
        "environment": environment,
        "summary": {
            "sessions": len(sessions),
            "pageViews": actions["page_view"],
            "checkoutSessions": len(checkout_sessions),
            "approvedPayments": approved,
            "abandonedCheckouts": len(abandoned),
            "draftsWithoutCheckout": drafts,
        },
        "funnel": funnel,
        "pages": [{"key": k, "count": n} for k, n in pages.most_common(12)],
        "actions": [{"key": k, "count": n} for k, n in actions.most_common()],
        "interest": [
            {
                "templateId": k,
                "title": templates.get(k, k),
                "views": len(v["views"]),
                "selections": len(v["selections"]),
            }
            for k, v in sorted(
                interest.items(), key=lambda i: (len(i[1]["selections"]), len(i[1]["views"])), reverse=True
            )
        ][:20],
        "bestSellers": [
            {"templateId": k, "title": templates.get(k, "Plantilla no identificada" if k == "unknown" else k), **v}
            for k, v in sorted(best.items(), key=lambda i: (i[1]["count"], i[1]["amount"]), reverse=True)
        ][:20],
        "abandoned": abandoned,
        "abandonedTotal": len(abandoned),
        "firstMeasuredAt": None,
    }


def renewal_report(projects, period, environment, include_overdue=True, now=None):
    today = (now or datetime.now(timezone.utc)).astimezone(CHILE).date()
    rows, awaiting, missing, overdue, upcoming = [], 0, 0, 0, 0
    for project in projects:
        if project.get("projectType") != "website":
            continue  # Invitations do not have the website annual/monthly contract.
        payments = [
            p
            for p in project.get("payments", [])
            if payment_environment(p) == environment and p.get("status") == "paid"
        ]
        if not payments:
            continue
        payment = min(payments, key=lambda p: p.get("paidAt") or p.get("createdAt") or "")
        subscription = project.get("subscription") or {}
        if subscription.get("status") == "cancelled":
            continue
        recorded = parsed_time(subscription.get("nextRenewalAt"))
        dates = [
            parsed_time(project.get("firstPublishedAt")),
            *[parsed_time(s.get("publishedAt")) for s in project.get("firstSnapshot", [])],
        ]
        first = min((d for d in dates if d), default=None)
        if not recorded and not first:
            awaiting += 1
            continue
        billing = payment.get("billingTerms") or {}
        months = billing.get("initialMonths")
        if not recorded and (not isinstance(months, int) or months <= 0 or months > 120):
            missing += 1
            continue
        due = recorded or add_months(first.astimezone(CHILE), months)
        due_date = due.astimezone(CHILE).date()
        past = due_date < today
        if not (period.start <= due_date <= period.end or include_overdue and past):
            continue
        days = (due_date - today).days
        overdue += past
        upcoming += not past
        amount = money(subscription.get("renewalAmount", billing.get("renewalAmount")))
        rows.append(
            {
                "projectId": project["id"],
                "title": project.get("title"),
                "email": project.get("ownerEmail"),
                "dueAt": due.isoformat(),
                "daysRemaining": days,
                "amount": float(amount) if amount is not None else None,
                "period": subscription.get("renewalPeriod") or billing.get("renewalPeriod"),
                "source": "recorded" if recorded else "contract_estimate",
                "status": "past_due_review" if past else "upcoming",
            }
        )
    rows.sort(key=lambda r: (r["dueAt"], r["projectId"]))
    return {
        "period": period.as_dict(),
        "environment": environment,
        "summary": {
            "upcoming": upcoming,
            "overdueToReview": overdue,
            "awaitingPublication": awaiting,
            "missingTerms": missing,
        },
        "renewals": rows,
        "total": len(rows),
    }


class InsightsService:
    def __init__(self, repository=None):
        self.repository = repository or DomainRepository()

    def behavior(self, period, environment):
        environment = resolve_report_environment(environment)
        report = behavior_report(
            self.repository.iter_analytics_events(period.since, period.until, environment),
            self.repository.iter_commercial_payments(period.since, period.until),
            self.repository.iter_reporting_projects(),
            self.repository.reporting_templates(),
            period,
            environment,
        )
        first = self.repository.collection("analytics_events").find_one(
            {"environment": environment}, {"_id": 0, "receivedAt": 1}, sort=[("receivedAt", 1)]
        )
        report["firstMeasuredAt"] = first.get("receivedAt") if first else None
        return report

    def renewals(self, period, environment, include_overdue=True):
        environment = resolve_report_environment(environment)
        return renewal_report(self.repository.iter_reporting_projects(), period, environment, include_overdue)
