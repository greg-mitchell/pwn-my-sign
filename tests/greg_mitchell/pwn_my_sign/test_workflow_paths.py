from collections.abc import Callable
from pathlib import Path
from unittest.mock import Mock

import pytest

from greg_mitchell.pwn_my_sign.workflow.paths import default_state_directory


@pytest.mark.parametrize("value", [None, "", "relative-state", "~/state"])
def test_default_state_directory_when_xdg_home_not_absolute_returns_home_display_directory(
    tmp_path: Path, value: str | None
) -> None:
    environment = {"XDG_STATE_HOME": value} if value is not None else {}

    result = default_state_directory(environment, home=lambda: tmp_path)

    assert result == tmp_path / ".local/state/pwn-my-sign/display"


def test_default_state_directory_when_xdg_home_absolute_returns_xdg_display_directory(tmp_path: Path) -> None:
    result = default_state_directory({"XDG_STATE_HOME": str(tmp_path / "xdg-state")})

    assert result == tmp_path / "xdg-state/pwn-my-sign/display"


def test_default_state_directory_when_xdg_home_absolute_calls_no_home_provider(tmp_path: Path) -> None:
    home = Mock(spec=Callable)

    default_state_directory({"XDG_STATE_HOME": str(tmp_path)}, home=home)

    home.assert_not_called()


def test_default_state_directory_when_xdg_home_missing_calls_home_provider(tmp_path: Path) -> None:
    home = Mock(spec=Callable, return_value=tmp_path)

    default_state_directory({}, home=home)

    home.assert_called_once_with()


def test_default_state_directory_when_home_unavailable_raises_home_error() -> None:
    home = Mock(spec=Callable, side_effect=RuntimeError("Home directory unavailable"))

    with pytest.raises(RuntimeError, match="Home directory unavailable"):
        default_state_directory({}, home=home)
