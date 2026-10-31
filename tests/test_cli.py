from __future__ import annotations

from pathlib import Path

import pytest

from epic_free_games_tracker.cli import build_parser, main


def _sample_path() -> Path:
    return Path(__file__).parent.parent / "examples" / "sample_response.json"


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["--version"])
    assert exc.value.code == 0


def test_filter_flags_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--all", "--free"])


def test_cli_from_sample_file_writes_csv(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "games.csv"
    code = main(["--input", str(_sample_path()), "--output", str(output)])
    assert code == 0
    assert output.exists()
    captured = capsys.readouterr().out
    assert "Example Quest" in captured
    assert "Found 2 games" in captured


def test_cli_all_shows_no_promotion_game(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "games.csv"
    code = main(["--input", str(_sample_path()), "--all", "--output", str(output)])
    assert code == 0
    captured = capsys.readouterr().out
    assert "Found 3 games" in captured
    assert "No Promotion Edition" in captured


def test_cli_no_save_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "games.csv"
    code = main(
        [
            "--input",
            str(_sample_path()),
            "--output",
            str(output),
            "--no-save",
        ]
    )
    assert code == 0
    assert not output.exists()


def test_cli_missing_input_file_returns_1(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(["--input", "does-not-exist.json", "--no-save"])
    assert code == 1
    # Errors go to stderr, so a piped stdout stays clean.
    captured = capsys.readouterr()
    assert "Error fetching games" in captured.err
    assert "Error fetching games" not in captured.out


def test_cli_empty_feed_returns_0(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    empty = tmp_path / "empty.json"
    empty.write_text(
        '{"data": {"Catalog": {"searchStore": {"elements": []}}}}',
        encoding="utf-8",
    )
    code = main(["--input", str(empty), "--no-save"])
    assert code == 0
    assert "No games found" in capsys.readouterr().err


def test_python_m_module_runs() -> None:
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "epic_free_games_tracker",
            "--input",
            str(_sample_path()),
            "--no-save",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "Example Quest" in result.stdout


def test_cli_default_csv_is_under_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    code = main(["--input", str(_sample_path())])
    assert code == 0
    assert (tmp_path / "output" / "epic_free_games.csv").exists()
