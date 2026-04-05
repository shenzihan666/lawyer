import json
from pathlib import Path

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_engine, get_session_factory
from app.services.contract_review import ContractReviewService


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    manifest_path = repo_root / "scripts" / "contract_review_seed_templates.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    settings = get_settings()
    Base.metadata.create_all(bind=get_engine())

    session = get_session_factory()()
    try:
        service = ContractReviewService(db=session, settings=settings)
        affected_ids = service.import_seed_templates(manifest)
        print(f"Imported or reused {len(affected_ids)} template(s).")
    finally:
        session.close()


if __name__ == "__main__":
    main()
