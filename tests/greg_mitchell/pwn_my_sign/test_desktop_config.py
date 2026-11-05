from pathlib import Path

import pytest

from greg_mitchell.pwn_my_sign.desktop.config import load_settings


@pytest.fixture
def configuration(tmp_path: Path) -> Path:
    path = tmp_path / "desktop.toml"
    path.write_text('command = ["./producer", "literal; $(argument)"]\ndevice = "test sign"\n')
    return path


def test_load_settings_when_working_directory_omitted_returns_configuration_directory(configuration: Path) -> None:
    result = load_settings(configuration)

    assert result.working_directory == configuration.parent


def test_load_settings_when_state_directory_omitted_returns_xdg_display_directory(
    configuration: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))

    result = load_settings(configuration)

    assert result.state_directory == tmp_path / "xdg-state/pwn-my-sign/display"


@pytest.mark.parametrize("xdg_state_home", [None, "", "relative-state"])
def test_load_settings_when_xdg_state_home_unusable_returns_home_state_directory(
    configuration: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, xdg_state_home: str | None
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    if xdg_state_home is None:
        monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    else:
        monkeypatch.setenv("XDG_STATE_HOME", xdg_state_home)

    result = load_settings(configuration)

    assert result.state_directory == tmp_path / "home/.local/state/pwn-my-sign/display"


def test_load_settings_when_directories_use_home_returns_expanded_directories(
    configuration: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    configuration.write_text(
        'command = ["./producer"]\ndevice = "test sign"\n'
        'working_directory = "~/checkout"\nstate_directory = "~/state"\n'
    )

    result = load_settings(configuration)

    assert (result.working_directory, result.state_directory) == (tmp_path / "home/checkout", tmp_path / "home/state")


@pytest.mark.parametrize("setting", ["working_directory", "state_directory"])
def test_load_settings_when_explicit_directory_relative_raises_path_error(
    configuration: Path, tmp_path: Path, setting: str
) -> None:
    working = "relative" if setting == "working_directory" else str(tmp_path)
    state = "relative" if setting == "state_directory" else str(tmp_path / "state")
    configuration.write_text(
        f'command = ["./producer"]\ndevice = "test sign"\n'
        f'working_directory = "{working}"\nstate_directory = "{state}"\n'
    )

    with pytest.raises(ValueError, match="absolute"):
        load_settings(configuration)


def test_load_settings_when_producer_relative_returns_executable_under_default_working_directory(
    configuration: Path,
) -> None:
    result = load_settings(configuration)

    assert result.command == (str(configuration.parent / "producer"), "literal; $(argument)")


def test_load_settings_when_producer_uses_home_returns_expanded_executable(
    configuration: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    configuration.write_text('command = ["~/bin/producer", "~/literal argument"]\ndevice = "test sign"\n')

    result = load_settings(configuration)

    assert result.command == (str(tmp_path / "home/bin/producer"), "~/literal argument")


def test_load_settings_when_example_copied_to_private_returns_private_producer(tmp_path: Path) -> None:
    example = Path(__file__).resolve().parents[3] / 'data/desktop.example.toml'
    configuration = tmp_path / 'private/desktop.toml'
    configuration.parent.mkdir()
    configuration.write_bytes(example.read_bytes())

    result = load_settings(configuration)

    assert result.command == (str(tmp_path / 'private/produce-image'),)
