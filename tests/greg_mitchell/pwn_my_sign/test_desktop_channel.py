from collections.abc import Callable
from io import BytesIO
from unittest.mock import Mock

import pytest

from greg_mitchell.pwn_my_sign.desktop.channel import MessageReader, MessageWriter
from greg_mitchell.pwn_my_sign.desktop.protocol import Acknowledgment, Action, ActionKind, Phase, View


@pytest.fixture
def acknowledgment() -> Acknowledgment:
    return Acknowledgment(version=1, id="button-1", submitted=True)


def test_receive_when_record_split_returns_complete_message(acknowledgment: Acknowledgment) -> None:
    data = acknowledgment.model_dump_json().encode() + b"\n"
    read = Mock(spec=Callable, side_effect=[data[:12], data[12:]])
    reader = MessageReader(42, Mock(spec=Callable), ready=Mock(spec=Callable, return_value=True), read=read)

    result = reader.receive(3)

    assert result == acknowledgment


def test_receive_when_two_records_share_chunk_calls_read_only_once(acknowledgment: Acknowledgment) -> None:
    read = Mock(spec=Callable, return_value=(acknowledgment.model_dump_json().encode() + b"\n") * 2)
    reader = MessageReader(42, Mock(spec=Callable), ready=Mock(spec=Callable, return_value=True), read=read)

    reader.receive(3)
    reader.receive(3)

    read.assert_called_once_with(42, 4096)


@pytest.mark.parametrize(
    "invalid",
    [
        b"not JSON\n",
        b'{"version":2,"type":"action","action":"upload","revision":1}\n',
        b'{"type":"action","action":"upload","revision":1}\n',
    ],
)
def test_receive_when_invalid_message_precedes_action_returns_valid_action(invalid: bytes) -> None:
    action = Action(version=1, action=ActionKind.CHECK, revision=7)
    read = Mock(spec=Callable, return_value=invalid + action.model_dump_json().encode() + b"\n")
    reader = MessageReader(42, Mock(spec=Callable), ready=Mock(spec=Callable, return_value=True), read=read)

    result = reader.receive(3)

    assert result == action


def test_receive_when_oversized_unterminated_record_arrives_returns_next_valid_message(
    acknowledgment: Acknowledgment,
) -> None:
    read = Mock(
        spec=Callable,
        side_effect=[b"x" * 4096] * 4 + [b"suffix\n" + acknowledgment.model_dump_json().encode() + b"\n"],
    )
    reader = MessageReader(42, Mock(spec=Callable), ready=Mock(spec=Callable, return_value=True), read=read)

    result = reader.receive(3)

    assert result == acknowledgment


def test_receive_when_no_input_returns_timeout() -> None:
    reader = MessageReader(42, Mock(spec=Callable), ready=Mock(spec=Callable, return_value=False))

    result = reader.receive(3)

    assert result is None


def test_receive_when_pipe_closed_raises_eof_error() -> None:
    reader = MessageReader(
        42,
        Mock(spec=Callable),
        ready=Mock(spec=Callable, return_value=True),
        read=Mock(spec=Callable, return_value=b""),
    )

    with pytest.raises(EOFError, match="closed its input"):
        reader.receive(3)


def test_receive_when_read_fails_raises_os_error() -> None:
    reader = MessageReader(
        42,
        Mock(spec=Callable),
        ready=Mock(spec=Callable, return_value=True),
        read=Mock(spec=Callable, side_effect=OSError("Pipe failed")),
    )

    with pytest.raises(OSError, match="Pipe failed"):
        reader.receive(3)


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


def test_receive_when_invalid_input_continues_after_deadline_returns_timeout(acknowledgment: Acknowledgment) -> None:
    read = Mock(spec=Callable, side_effect=[b"invalid JSON\n", acknowledgment.model_dump_json().encode() + b"\n"])
    reader = MessageReader(
        42,
        Mock(spec=Callable),
        ready=Mock(spec=Callable, return_value=True),
        read=read,
        clock=Mock(spec=Callable, side_effect=[0, 0, 4]),
    )

    result = reader.receive(3)

    assert result is None
