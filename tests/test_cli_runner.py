"""Click CliRunner tests for groundcrew.cli (no subprocess)."""

from __future__ import annotations

from click.testing import CliRunner

from groundcrew.cli import main


def test_help():
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "groundcrew" in result.output.lower()


def test_log_empty(tmp_path):
    db = str(tmp_path / "r.db")
    result = CliRunner().invoke(main, ["--db", db, "log"])
    assert result.exit_code == 0


def test_status(tmp_path):
    db = str(tmp_path / "r.db")
    result = CliRunner().invoke(main, ["--db", db, "status", "--root", str(tmp_path)])
    assert result.exit_code == 0


def test_capture(tmp_path):
    db = str(tmp_path / "r.db")
    (tmp_path / "seed.txt").write_text("seed")
    result = CliRunner().invoke(
        main,
        ["--db", db, "capture", "--root", str(tmp_path), "--verb", "write", "--target", "test.txt"],
    )
    assert result.exit_code == 0
    assert "Captured receipt" in result.output


def test_diff_existing(tmp_path):
    db = str(tmp_path / "r.db")
    work = tmp_path / "work"
    work.mkdir()
    (work / "seed.txt").write_text("seed")
    runner = CliRunner()
    cap = runner.invoke(
        main,
        ["--db", db, "capture", "--root", str(work), "--verb", "write", "--target", "test.txt"],
    )
    assert cap.exit_code == 0
    receipt_id = cap.output.split("Captured receipt ")[1].split()[0]
    result = runner.invoke(main, ["--db", db, "diff", receipt_id])
    assert result.exit_code == 0


def test_diff_nonexistent(tmp_path):
    db = str(tmp_path / "r.db")
    result = CliRunner().invoke(main, ["--db", db, "diff", "doesnotexist"])
    assert result.exit_code != 0


def test_capture_with_run(tmp_path):
    db = str(tmp_path / "r.db")
    work = tmp_path / "work"
    work.mkdir()
    result = CliRunner().invoke(
        main,
        [
            "--db",
            db,
            "capture",
            "--root",
            str(work),
            "--verb",
            "create",
            "--target",
            "new.txt",
            "--run",
            "echo hi > new.txt",
        ],
    )
    assert result.exit_code == 0
    assert (work / "new.txt").exists()


def test_capture_with_failing_run(tmp_path):
    db = str(tmp_path / "r.db")
    work = tmp_path / "work"
    work.mkdir()
    result = CliRunner().invoke(
        main,
        [
            "--db",
            db,
            "capture",
            "--root",
            str(work),
            "--verb",
            "fail",
            "--target",
            "x",
            "--run",
            "exit 1",
        ],
    )
    assert result.exit_code == 0
    assert "Captured receipt" in result.output
