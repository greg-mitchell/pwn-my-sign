import asyncio
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from bleak import BleakClient, BleakScanner
from click.testing import CliRunner
from PIL import Image

from greg_mitchell.pwn_my_sign.cli.mysign import main as mysign
from greg_mitchell.pwn_my_sign.device.operations import DeviceOperations, ImageInputError
from greg_mitchell.pwn_my_sign.transport import send_frame


class InputStream(BytesIO):
    def __init__(self, data: bytes = b"", *, read_error: bool = False) -> None:
        super().__init__(data)
        self.read_error = read_error
        self.read_count = 0

    def read(self, size: int | None = -1) -> bytes:
        if size != 0:
            self.read_count += 1
            if self.read_error:
                raise OSError("cannot read stream")
        return super().read(size)


@pytest.fixture
def png() -> bytes:
    stream = BytesIO()
    Image.new("L", (1280, 720), 255).save(stream, format="PNG")
    return stream.getvalue()


@pytest.fixture(params=("empty", "malformed", "jpeg", "truncated", "dimensions", "animated", "read-error"))
def invalid_stream(request: pytest.FixtureRequest, png: bytes) -> BytesIO:
    stream = BytesIO()
    match request.param:
        case "empty":
            return stream
        case "malformed":
            return BytesIO(b"not PNG")
        case "jpeg":
            Image.new("L", (1280, 720)).save(stream, format="JPEG")
        case "truncated":
            return BytesIO(png[:-4])
        case "dimensions":
            Image.new("L", (1279, 720)).save(stream, format="PNG")
        case "animated":
            Image.new("L", (1280, 720), 0).save(
                stream, format="PNG", save_all=True, append_images=[Image.new("L", (1280, 720), 255)]
            )
        case "read-error":
            return InputStream(read_error=True)
    stream.seek(0)
    return stream


def test_upload_when_png_stdin_is_valid_calls_sender_with_encoded_frame(png: bytes) -> None:
    scanner = Mock(spec=BleakScanner)
    client = MagicMock(spec=BleakClient)
    client.__aenter__.return_value = client
    send = AsyncMock(spec=send_frame)
    sleep = AsyncMock(spec=asyncio.sleep)
    operations = DeviceOperations(
        scanner=scanner, client_factory=Mock(spec=BleakClient, return_value=client), send=send, sleep=sleep
    )

    asyncio.run(
        operations.upload(
            "test-sign",
            image_path=None,
            image_stream=BytesIO(png),
            frame_path=None,
            timeout=7,
            packet_delay=0.05,
            report=Mock(spec=print),
        )
    )

    send.assert_awaited_once_with(client, b"\xff" * 460800, 0.05, sleep)


def test_upload_when_png_stdin_is_valid_calls_reader_once(png: bytes) -> None:
    scanner = Mock(spec=BleakScanner)
    scanner.find_device_by_filter.return_value = None
    stream = Mock(spec=BytesIO, read=Mock(return_value=png))

    with pytest.raises(TimeoutError):
        asyncio.run(
            DeviceOperations(scanner=scanner).upload(
                "test-sign",
                image_path=None,
                image_stream=stream,
                frame_path=None,
                timeout=7,
                packet_delay=0.05,
                report=Mock(spec=print),
            )
        )

    stream.read.assert_called_once_with()


def test_upload_when_png_stdin_is_invalid_raises_image_input_error(invalid_stream: BytesIO) -> None:
    scanner = Mock(spec=BleakScanner)

    with pytest.raises(ImageInputError):
        asyncio.run(
            DeviceOperations(scanner=scanner).upload(
                "test-sign",
                image_path=None,
                image_stream=invalid_stream,
                frame_path=None,
                timeout=7,
                packet_delay=0.05,
                report=Mock(spec=print),
            )
        )


def test_upload_when_png_stdin_is_invalid_calls_no_prompt(invalid_stream: BytesIO) -> None:
    report = Mock(spec=print)

    with pytest.raises(ImageInputError):
        asyncio.run(
            DeviceOperations(scanner=Mock(spec=BleakScanner)).upload(
                "test-sign",
                image_path=None,
                image_stream=invalid_stream,
                frame_path=None,
                timeout=7,
                packet_delay=0.05,
                report=report,
            )
        )

    report.assert_not_called()


def test_upload_when_png_stdin_is_invalid_calls_no_discovery(invalid_stream: BytesIO) -> None:
    scanner = Mock(spec=BleakScanner)

    with pytest.raises(ImageInputError):
        asyncio.run(
            DeviceOperations(scanner=scanner).upload(
                "test-sign",
                image_path=None,
                image_stream=invalid_stream,
                frame_path=None,
                timeout=7,
                packet_delay=0.05,
                report=Mock(spec=print),
            )
        )

    assert scanner.mock_calls == []


def test_upload_when_stream_conflicts_with_path_calls_no_reader() -> None:
    stream = Mock(spec=BytesIO)

    with pytest.raises(ImageInputError):
        asyncio.run(
            DeviceOperations(scanner=Mock(spec=BleakScanner)).upload(
                "test-sign",
                image_path=Path("card.png"),
                image_stream=stream,
                frame_path=None,
                timeout=7,
                packet_delay=0.05,
                report=Mock(spec=print),
            )
        )

    stream.read.assert_not_called()


def test_device_send_when_png_stdin_is_selected_calls_uploader_with_binary_stream(png: bytes) -> None:
    operations = Mock(spec=DeviceOperations)

    CliRunner().invoke(
        mysign,
        ["device", "send", "--device", "test-sign", "--image", "-"],
        input=png,
        obj=operations,
        catch_exceptions=False,
    )

    assert (
        operations.upload.call_args.kwargs["image_path"],
        operations.upload.call_args.kwargs["image_stream"].getvalue(),
    ) == (None, png)


def test_device_send_when_png_stdin_is_valid_returns_success(png: bytes) -> None:
    scanner = Mock(spec=BleakScanner)
    client = MagicMock(spec=BleakClient)
    operations = DeviceOperations(
        scanner=scanner, client_factory=Mock(spec=BleakClient, return_value=client), send=AsyncMock(spec=send_frame)
    )

    result = CliRunner().invoke(
        mysign, ["device", "send", "--device", "test-sign", "--image", "-"], input=png, obj=operations
    )

    assert result.exit_code == 0


def test_device_send_when_png_stdin_is_valid_returns_no_stdout(png: bytes) -> None:
    operations = DeviceOperations(
        scanner=Mock(spec=BleakScanner),
        client_factory=Mock(spec=BleakClient, return_value=MagicMock(spec=BleakClient)),
        send=AsyncMock(spec=send_frame),
    )

    result = CliRunner().invoke(
        mysign, ["device", "send", "--device", "test-sign", "--image", "-"], input=png, obj=operations
    )

    assert result.stdout_bytes == b""


def test_upload_when_file_image_is_jpeg_calls_sender_with_encoded_frame(tmp_path: Path) -> None:
    image_path = tmp_path / "card.jpg"
    Image.new("L", (1280, 720), 255).save(image_path, format="JPEG")
    client = MagicMock(spec=BleakClient)
    client.__aenter__.return_value = client
    send = AsyncMock(spec=send_frame)
    sleep = AsyncMock(spec=asyncio.sleep)
    operations = DeviceOperations(
        scanner=Mock(spec=BleakScanner),
        client_factory=Mock(spec=BleakClient, return_value=client),
        send=send,
        sleep=sleep,
    )

    asyncio.run(
        operations.upload(
            "test-sign", image_path=image_path, frame_path=None, timeout=7, packet_delay=0.05, report=Mock(spec=print)
        )
    )

    send.assert_awaited_once_with(client, b"\xff" * 460800, 0.05, sleep)


def test_device_send_when_png_stdin_is_invalid_returns_no_stdout(invalid_stream: BytesIO) -> None:
    operations = DeviceOperations(scanner=Mock(spec=BleakScanner))

    result = CliRunner().invoke(
        mysign, ["device", "send", "--device", "test-sign", "--image", "-"], input=invalid_stream, obj=operations
    )

    assert (result.exit_code, result.stdout_bytes) == (1, b"")


def test_device_send_when_stream_read_fails_returns_diagnostic_on_stderr() -> None:
    operations = Mock(spec=DeviceOperations)
    operations.upload.side_effect = ImageInputError("cannot read stream")

    result = CliRunner().invoke(
        mysign, ["device", "send", "--device", "test-sign", "--image", "-"], input=b"data", obj=operations
    )

    assert result.stderr == "Error: Cannot read PNG stdin: cannot read stream\n"


def test_device_send_when_stdin_and_frame_are_selected_calls_no_uploader() -> None:
    operations = Mock(spec=DeviceOperations)

    CliRunner().invoke(
        mysign,
        ["device", "send", "--device", "test-sign", "--image", "-", "--frame", "frame.bin"],
        input=b"unused",
        obj=operations,
    )

    operations.upload.assert_not_called()


def test_device_send_when_stdin_and_frame_are_selected_calls_no_stream_read() -> None:
    stream = InputStream(b"unused")

    CliRunner().invoke(
        mysign,
        ["device", "send", "--device", "test-sign", "--image", "-", "--frame", "frame.bin"],
        input=stream,
        obj=Mock(spec=DeviceOperations),
    )

    assert stream.read_count == 0
