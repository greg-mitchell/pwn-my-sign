from collections.abc import Callable
from io import BytesIO
from queue import Empty, Queue
from unittest.mock import Mock, call

import pytest

from greg_mitchell.pwn_my_sign.desktop.channel import InputIssue, LinePump, MessageReader, MessageWriter, PipeInput
from greg_mitchell.pwn_my_sign.desktop.protocol import MAX_RECORD_BYTES, Acknowledgment, Action, ActionKind, Phase, View


@pytest.fixture
def acknowledgment() -> Acknowledgment:
    return Acknowledgment(version=1, id="button-1", submitted=True)


@pytest.fixture
def messages() -> Queue[PipeInput]:
    return Queue(maxsize=16)


def test_run_when_complete_record_calls_delivery_with_line(acknowledgment: Acknowledgment) -> None:
    line = acknowledgment.model_dump_json().encode() + b"\n"
    deliver = Mock(spec=Callable)

    LinePump(BytesIO(line), deliver).run()

    assert deliver.call_args_list[0] == call(line)


def test_run_when_stream_empty_calls_delivery_with_eof() -> None:
    deliver = Mock(spec=Callable)

    LinePump(BytesIO(), deliver).run()

    assert isinstance(deliver.call_args.args[0], EOFError)


def test_run_when_stream_fails_calls_delivery_with_read_error() -> None:
    stream = Mock(spec=BytesIO, **{"readline.side_effect": OSError("Pipe failed")})
    deliver = Mock(spec=Callable)

    LinePump(stream, deliver).run()

    assert str(deliver.call_args.args[0]) == "Pipe failed"


def test_run_when_reading_calls_stream_with_bounded_line_limit() -> None:
    stream = Mock(spec=BytesIO, **{"readline.return_value": b""})

    LinePump(stream, Mock(spec=Callable)).run()

    stream.readline.assert_called_once_with(MAX_RECORD_BYTES + 1)


def test_run_when_partial_record_at_eof_calls_incomplete_diagnostic() -> None:
    deliver = Mock(spec=Callable)

    LinePump(BytesIO(b'{"version":1'), deliver).run()

    assert deliver.call_args_list[0] == call(InputIssue.INCOMPLETE)


def test_run_when_oversized_record_at_eof_calls_incomplete_diagnostic() -> None:
    deliver = Mock(spec=Callable)

    LinePump(BytesIO(b"x" * (MAX_RECORD_BYTES * 2)), deliver).run()

    assert deliver.call_args_list[0] == call(InputIssue.INCOMPLETE)


def test_run_when_oversized_record_terminated_calls_oversized_diagnostic() -> None:
    deliver = Mock(spec=Callable)

    LinePump(BytesIO(b"x" * MAX_RECORD_BYTES + b"\n"), deliver).run()

    assert deliver.call_args_list[0] == call(InputIssue.OVERSIZED)


def test_receive_when_message_queued_returns_valid_message(
    acknowledgment: Acknowledgment, messages: Queue[PipeInput]
) -> None:
    messages.put(acknowledgment.model_dump_json().encode() + b"\n")
    reader = MessageReader(messages, Mock(spec=Callable))

    result = reader.receive(3)

    assert result == acknowledgment


def test_receive_when_zero_timeout_and_message_queued_returns_valid_message(
    acknowledgment: Acknowledgment, messages: Queue[PipeInput]
) -> None:
    messages.put(acknowledgment.model_dump_json().encode() + b"\n")
    reader = MessageReader(messages, Mock(spec=Callable))

    result = reader.receive(0)

    assert result == acknowledgment


@pytest.mark.parametrize(
    "invalid",
    [
        b"not JSON\n",
        b"\xff\n",
        b'{"version":2,"type":"action","action":"upload","revision":1}\n',
        b'{"type":"action","action":"upload","revision":1}\n',
    ],
)
def test_receive_when_invalid_message_precedes_action_returns_valid_action(
    invalid: bytes, messages: Queue[PipeInput]
) -> None:
    action = Action(version=1, action=ActionKind.CHECK, revision=7)
    messages.put(invalid)
    messages.put(action.model_dump_json().encode() + b"\n")
    reader = MessageReader(messages, Mock(spec=Callable))

    result = reader.receive(3)

    assert result == action


def test_receive_when_oversized_record_precedes_message_returns_next_message(
    acknowledgment: Acknowledgment, messages: Queue[PipeInput]
) -> None:
    stream = BytesIO(b"x" * (MAX_RECORD_BYTES * 3) + b"\n" + acknowledgment.model_dump_json().encode() + b"\n")
    LinePump(stream, messages.put).run()
    reader = MessageReader(messages, Mock(spec=Callable))

    result = reader.receive(3)

    assert result == acknowledgment


def test_receive_when_record_exactly_at_limit_returns_message(
    acknowledgment: Acknowledgment, messages: Queue[PipeInput]
) -> None:
    data = acknowledgment.model_dump_json().encode()
    stream = BytesIO(data + b" " * (MAX_RECORD_BYTES - len(data) - 1) + b"\n")
    LinePump(stream, messages.put).run()
    reader = MessageReader(messages, Mock(spec=Callable))

    result = reader.receive(3)

    assert result == acknowledgment


def test_receive_when_framing_issue_queued_calls_report(messages: Queue[PipeInput]) -> None:
    messages.put(InputIssue.OVERSIZED)
    report = Mock(spec=Callable)
    reader = MessageReader(messages, report)

    reader.receive(0)

    report.assert_called_once_with("Ignoring oversized desktop message.")


def test_receive_when_invalid_message_queued_calls_report(messages: Queue[PipeInput]) -> None:
    messages.put(b"not JSON\n")
    report = Mock(spec=Callable)
    reader = MessageReader(messages, report)

    reader.receive(0)

    assert report.call_args.args[0].startswith("Ignoring invalid desktop message:")


def test_receive_when_no_input_returns_timeout() -> None:
    messages = Mock(spec=Queue, **{"get.side_effect": Empty})
    reader = MessageReader(messages, Mock(spec=Callable))

    result = reader.receive(3)

    assert result is None


def test_receive_when_waiting_calls_queue_with_remaining_timeout() -> None:
    messages = Mock(spec=Queue, **{"get.side_effect": Empty})
    reader = MessageReader(messages, Mock(spec=Callable), clock=Mock(spec=Callable, side_effect=[10, 11]))

    reader.receive(3)

    messages.get.assert_called_once_with(timeout=2)


def test_receive_when_pipe_closed_raises_eof_error(messages: Queue[PipeInput]) -> None:
    messages.put(EOFError("The desktop application closed its input pipe."))
    reader = MessageReader(messages, Mock(spec=Callable))

    with pytest.raises(EOFError, match="closed its input"):
        reader.receive(3)


def test_receive_when_read_failed_raises_os_error(messages: Queue[PipeInput]) -> None:
    messages.put(OSError("Pipe failed"))
    reader = MessageReader(messages, Mock(spec=Callable))

    with pytest.raises(OSError, match="Pipe failed"):
        reader.receive(3)


def test_receive_when_parent_closed_before_pump_observes_eof_raises_eof_error(messages: Queue[PipeInput]) -> None:
    reader = MessageReader(messages, Mock(spec=Callable), parent_closed=lambda: True)

    with pytest.raises(EOFError, match="closed its input"):
        reader.receive(0)


def test_receive_when_parent_closed_with_old_action_queued_raises_eof_error(messages: Queue[PipeInput]) -> None:
    messages.put(Action(version=1, action=ActionKind.CHECK, revision=7).model_dump_json().encode() + b"\n")
    reader = MessageReader(messages, Mock(spec=Callable), parent_closed=lambda: True)

    with pytest.raises(EOFError, match="closed its input"):
        reader.receive(0)


def test_receive_when_positive_timeout_calls_no_parent_probe(
    acknowledgment: Acknowledgment, messages: Queue[PipeInput]
) -> None:
    messages.put(acknowledgment.model_dump_json().encode() + b"\n")
    parent_closed = Mock(spec=Callable, return_value=False)
    reader = MessageReader(messages, Mock(spec=Callable), parent_closed=parent_closed)

    reader.receive(3)

    parent_closed.assert_not_called()


def test_receive_when_buffered_invalid_input_exhausts_deadline_returns_timeout(
    acknowledgment: Acknowledgment, messages: Queue[PipeInput]
) -> None:
    messages.put(b"invalid JSON\n")
    messages.put(acknowledgment.model_dump_json().encode() + b"\n")
    reader = MessageReader(messages, Mock(spec=Callable), clock=Mock(spec=Callable, side_effect=[0, 0, 4]))

    result = reader.receive(3)

    assert result is None


def test_send_when_view_emitted_returns_one_complete_newline_delimited_record() -> None:
    stream = BytesIO()
    view = View(revision=0, phase=Phase.STARTING, message="Starting sign workflow.")

    MessageWriter(stream).send(view)

    assert stream.getvalue() == (
        b'{"version":1,"type":"view","revision":0,"phase":"starting","message":"Starting sign workflow.",'
        b'"upload_available":false,"retained":false,"last_check":null,"last_result":null,"error":null}\n'
    )


def test_send_when_view_emitted_calls_flush() -> None:
    stream = Mock(spec=BytesIO)

    MessageWriter(stream).send(View(revision=0, phase=Phase.STARTING, message="Starting."))

    stream.flush.assert_called_once_with()


def test_send_when_output_exceeds_limit_calls_no_write() -> None:
    stream = Mock(spec=BytesIO)
    view = View(revision=0, phase=Phase.STARTING, message="Starting.", last_check="x" * 17000)

    with pytest.raises(ValueError, match="exceeds 16 KiB"):
        MessageWriter(stream).send(view)

    stream.write.assert_not_called()
