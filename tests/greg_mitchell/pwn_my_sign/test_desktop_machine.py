import pytest

from greg_mitchell.pwn_my_sign.desktop.machine import (
    Decision,
    DesktopState,
    Effect,
    Event,
    EventKind,
    Failure,
    PollResult,
    transition,
)
from greg_mitchell.pwn_my_sign.desktop.protocol import Phase


@pytest.mark.parametrize("phase", [Phase.CHECKING, Phase.PREPARING_UPLOAD, Phase.WAITING_FOR_BUTTON, Phase.SENDING])
def test_transition_when_busy_receives_upload_returns_no_work(phase: Phase) -> None:
    state = DesktopState(phase=phase)

    result = transition(state, Event(kind=EventKind.UPLOAD))

    assert result == Decision(state, publish=False)


def test_transition_when_up_to_date_receives_upload_returns_no_work() -> None:
    state = DesktopState(phase=Phase.UP_TO_DATE)

    result = transition(state, Event(kind=EventKind.UPLOAD))

    assert result == Decision(state, publish=False)


def test_transition_when_failed_poll_has_no_retained_image_returns_no_upload() -> None:
    state = DesktopState(phase=Phase.POLL_FAILED, error="Producer failed")

    result = transition(state, Event(kind=EventKind.UPLOAD))

    assert result == Decision(state, publish=False)


def test_transition_when_retained_image_selected_returns_upload_effect() -> None:
    state = DesktopState(phase=Phase.POLL_FAILED, error="Producer failed", retained=True)

    result = transition(state, Event(kind=EventKind.UPLOAD))

    assert result == Decision(DesktopState(phase=Phase.PREPARING_UPLOAD), (Effect.UPLOAD,))


def test_transition_when_unsent_check_completes_returns_nonactionable_history_check() -> None:
    state = DesktopState(phase=Phase.CHECKING)

    result = transition(
        state, PollResult(kind=EventKind.POLL_UNSENT, checked_at="2026-11-05T12:00:00+00:00", fingerprint="a" * 64)
    )

    assert result == Decision(
        DesktopState(phase=Phase.CHECKING, last_check="2026-11-05T12:00:00+00:00", fingerprint="a" * 64),
        (Effect.READ_REMINDER,),
        publish=False,
    )


def test_transition_when_update_notification_denied_returns_no_history_write() -> None:
    state = DesktopState(phase=Phase.CHECKING, fingerprint="a" * 64)

    result = transition(state, Failure(kind=EventKind.UPDATE_NOTIFICATION_FAILED, error="Notifications disabled"))

    assert result == Decision(
        DesktopState(phase=Phase.UPDATE_AVAILABLE, fingerprint="a" * 64, error="Notifications disabled"),
        (Effect.REPORT, Effect.SCHEDULE),
    )


def test_transition_when_button_ready_returns_required_notification_effect() -> None:
    state = DesktopState(phase=Phase.PREPARING_UPLOAD)

    result = transition(state, Event(kind=EventKind.BUTTON_READY))

    assert result == Decision(DesktopState(phase=Phase.WAITING_FOR_BUTTON), (Effect.NOTIFY_BUTTON,))


def test_transition_when_completion_notification_fails_returns_completed_result() -> None:
    state = DesktopState(phase=Phase.COMPLETED, last_result="Transfer completed.")

    result = transition(state, Failure(kind=EventKind.PRESENTATION_FAILED, error="Notifications disabled"))

    assert result == Decision(
        DesktopState(phase=Phase.COMPLETED, last_result="Transfer completed.", error="Notifications disabled"),
        (Effect.REPORT,),
    )


def test_transition_when_presentation_fails_returns_retained_image_context() -> None:
    state = DesktopState(phase=Phase.POLL_FAILED, retained=True, error="Producer failed")

    result = transition(state, Failure(kind=EventKind.PRESENTATION_FAILED, error="Presentation failed"))

    assert result.state == DesktopState(phase=Phase.POLL_FAILED, retained=True, error="Presentation failed")
