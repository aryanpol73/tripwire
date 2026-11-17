import pytest

from tripwire import __version__
from tripwire.cli import main


def test_version(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"tripwire {__version__}"


def test_no_arguments_prints_help(capsys):
    assert main([]) == 0
    assert "usage: tripwire" in capsys.readouterr().out
