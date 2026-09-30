import pytest

from ripple import __version__
from ripple.cli import main


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_no_command_prints_help(capsys):
    assert main([]) == 0
    assert "select" in capsys.readouterr().out


def test_unimplemented_command_fails_loudly():
    assert main(["select"]) == 1