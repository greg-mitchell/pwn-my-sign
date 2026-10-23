import json
from pathlib import Path
from unittest.mock import ANY, Mock

import pytest
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from click.testing import CliRunner
from PIL import Image

from greg_mitchell.pwn_my_sign.cli.mysign import main as mysign
from greg_mitchell.pwn_my_sign.device.operations import DeviceOperations
from greg_mitchell.pwn_my_sign.images.test_card import make_test_card


def test_device_scan_when_scanning_calls_discovery_with_timeout() -> None:
    operations = Mock(spec=DeviceOperations)
    operations.scan.return_value = ()

    CliRunner().invoke(mysign, ["device", "scan", "--timeout", "7"], obj=operations, catch_exceptions=False)

    operations.scan.assert_awaited_once_with(7)


def test_device_scan_when_a_device_is_discovered_returns_record_on_stdout() -> None:
    device = Mock(spec=BLEDevice, address="test-address")
    device.name = "fallback-name"
    advertisement = Mock(spec=AdvertisementData, local_name="test-sign", rssi=-42)
    operations = Mock(spec=DeviceOperations)
    operations.scan.return_value = ((device, advertisement),)

    result = CliRunner().invoke(mysign, ["device", "scan"], obj=operations)

    assert result.stdout == "test-address  'test-sign'  RSSI -42\n"


def test_device_scan_when_scanning_returns_button_prompt_on_stderr() -> None:
    operations = Mock(spec=DeviceOperations)
    operations.scan.return_value = ()

    result = CliRunner().invoke(mysign, ["device", "scan"], obj=operations)

    assert result.stderr == "Scanning; press the sign's button now.\n"


@pytest.mark.parametrize("source", ("--image", "--frame"))
def test_device_send_when_source_is_selected_calls_uploader_with_defaults(source: str) -> None:
    operations = Mock(spec=DeviceOperations)

    CliRunner().invoke(
        mysign, ["device", "send", "--device", "test-sign", source, "input.bin"], obj=operations, catch_exceptions=False
    )

    operations.upload.assert_awaited_once_with(
        "test-sign",
        image_path=Path("input.bin") if source == "--image" else None,
        image_stream=None,
        frame_path=Path("input.bin") if source == "--frame" else None,
        timeout=60,
        packet_delay=0.05,
        report=ANY,
    )


def test_device_send_when_options_are_selected_calls_uploader_with_options() -> None:
    operations = Mock(spec=DeviceOperations)

    CliRunner().invoke(
        mysign,
        ["device", "send", "--device", "test-sign", "--image", "image.png", "--timeout", "9", "--packet-delay", "0.1"],
        obj=operations,
        catch_exceptions=False,
    )

    operations.upload.assert_awaited_once_with(
        "test-sign",
        image_path=Path("image.png"),
        image_stream=None,
        frame_path=None,
        timeout=9,
        packet_delay=0.1,
        report=ANY,
    )


@pytest.mark.parametrize(
    "arguments",
    (
        ["--device", "test-sign"],
        ["--device", "test-sign", "--image", "image.png", "--frame", "frame.bin"],
        ["--image", "image.png"],
        ["--device", "test-sign", "--image", "image.png", "--timeout", "0"],
        ["--device", "test-sign", "--image", "image.png", "--packet-delay", "-0.1"],
    ),
)
def test_device_send_when_arguments_are_invalid_returns_usage_error(arguments: list[str]) -> None:
    result = CliRunner().invoke(mysign, ["device", "send", *arguments])

    assert result.exit_code == 2


def test_device_send_when_upload_fails_returns_failure() -> None:
    operations = Mock(spec=DeviceOperations)
    operations.upload.side_effect = TimeoutError("not found")

    result = CliRunner().invoke(
        mysign, ["device", "send", "--device", "test-sign", "--image", "image.png"], obj=operations
    )

    assert isinstance(result.exception, TimeoutError)


def test_image_test_card_when_font_is_selected_calls_builder_with_font(tmp_path: Path) -> None:
    builder = Mock(spec=make_test_card, return_value=Image.new("L", (1280, 720)))

    CliRunner().invoke(
        mysign,
        ["image", "test-card", "--font", "selected.ttf", "--output", str(tmp_path / "test.png")],
        obj=builder,
        catch_exceptions=False,
    )

    assert builder.call_args.args[2] == Path("selected.ttf")


def test_image_test_card_when_image_is_built_returns_matching_id_metadata(tmp_path: Path) -> None:
    builder = Mock(spec=make_test_card, return_value=Image.new("L", (1280, 720)))
    output = tmp_path / "cards" / "test.png"

    result = CliRunner().invoke(
        mysign, ["image", "test-card", "--output", str(output)], obj=builder, catch_exceptions=False
    )

    metadata = json.loads(output.with_suffix(".json").read_text())
    assert result.stdout == f"Created {output}: SENT FROM MAC / {metadata['test_id']}\n"


def test_image_test_card_when_builder_fails_returns_failure(tmp_path: Path) -> None:
    builder = Mock(spec=make_test_card, side_effect=OSError("missing font"))

    result = CliRunner().invoke(mysign, ["image", "test-card", "--output", str(tmp_path / "test.png")], obj=builder)

    assert isinstance(result.exception, OSError)


@pytest.mark.parametrize(
    ("arguments", "commands"),
    (
        (["--help"], ("device", "github", "image")),
        (["device", "--help"], ("scan", "send")),
        (["image", "--help"], ("make", "match", "test-card")),
        (["github", "--help"], ("status",)),
    ),
)
def test_mysign_when_group_help_is_requested_returns_available_commands(
    arguments: list[str], commands: tuple[str, ...]
) -> None:
    result = CliRunner().invoke(mysign, arguments, catch_exceptions=False)

    assert tuple(line.split()[0] for line in result.stdout.split("Commands:\n")[1].splitlines()) == commands


@pytest.mark.parametrize(
    "arguments",
    (
        ["--help"],
        ["device", "--help"],
        ["image", "--help"],
        ["device", "scan", "--help"],
        ["device", "send", "--help"],
        ["image", "test-card", "--help"],
        ["image", "make", "--help"],
    ),
)
def test_mysign_when_help_is_requested_calls_no_device_operations(arguments: list[str]) -> None:
    operations = Mock(spec=DeviceOperations)

    CliRunner().invoke(mysign, arguments, obj=operations, catch_exceptions=False)

    assert operations.mock_calls == []


@pytest.mark.parametrize("arguments", (["unknown"], ["device", "unknown"], ["image", "unknown"], ["upload"]))
def test_mysign_when_command_is_unknown_returns_usage_error(arguments: list[str]) -> None:
    result = CliRunner().invoke(mysign, arguments)

    assert result.exit_code == 2
