from app.core.config import get_settings
from app.modules.pricing.service import ensure_pricing_seed


def main() -> None:
    settings = get_settings()
    stats = ensure_pricing_seed()
    print(
        f"pricing sync complete | db={settings.mongodb_db_name} "
        f"insertedPlans={stats.insertedPlans} skippedPlans={stats.skippedPlans} "
        f"insertedComponents={stats.insertedComponents} skippedComponents={stats.skippedComponents} "
        f"insertedTemplateCategories={stats.insertedTemplateCategories} skippedTemplateCategories={stats.skippedTemplateCategories}"
    )


if __name__ == "__main__":
    main()
