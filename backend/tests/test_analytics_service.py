from app.core.config import get_settings
from app.db.session import get_session_factory
from app.models import SystemAnalyticsEvent, SystemTrajectoryRun, SystemTrajectoryStep
from app.services.analytics import AnalyticsService


def test_analytics_service_persists_event_and_trajectory(client) -> None:
    session = get_session_factory()()
    try:
        service = AnalyticsService(session, get_settings())
        event = service.record_event(
            category="test",
            event_name="analytics_smoke",
            status="success",
            trace_id="trace-1",
            resource_type="unit",
            resource_id="case-1",
            payload={"hello": "world"},
        )
        run = service.start_run(
            run_kind="unit_test",
            trace_id="trace-1",
            resource_type="unit",
            resource_id="case-1",
            metadata={"source": "pytest"},
        )
        step = service.append_step(
            run.id,
            step_key="phase-1",
            title="Phase 1",
            status="done",
            payload={"ok": True},
        )
        service.finish_run(
            run.id,
            status="completed",
            summary={"step_count": 1},
        )

        persisted_event = session.get(SystemAnalyticsEvent, event.id)
        persisted_run = session.get(SystemTrajectoryRun, run.id)
        persisted_step = session.get(SystemTrajectoryStep, step.id)

        assert persisted_event is not None
        assert persisted_event.category == "test"
        assert persisted_event.payload_json["hello"] == "world"

        assert persisted_run is not None
        assert persisted_run.status == "completed"
        assert persisted_run.summary_json["step_count"] == 1

        assert persisted_step is not None
        assert persisted_step.step_key == "phase-1"
        assert persisted_step.payload_json["ok"] is True
    finally:
        session.close()
