import pytest


def test_snapshot_parses():
    from phoenix.cli import build_parser
    args = build_parser().parse_args(["snapshot"])
    assert args.command == "snapshot"


def test_restore_flags_parse_correctly():
    from phoenix.cli import build_parser
    args = build_parser().parse_args(["restore", "--yes", "--skip-aur"])
    assert args.command == "restore"
    assert args.yes is True
    assert args.skip_aur is True


def test_restore_flags_default_false():
    from phoenix.cli import build_parser
    args = build_parser().parse_args(["restore"])
    assert args.yes is False
    assert args.skip_aur is False


def test_status_parses():
    from phoenix.cli import build_parser
    args = build_parser().parse_args(["status"])
    assert args.command == "status"


def test_status_content_and_resolve_flags_default_false():
    from phoenix.cli import build_parser
    args = build_parser().parse_args(["status"])
    assert args.content is False
    assert args.resolve is False


def test_status_content_flag_parses():
    from phoenix.cli import build_parser
    args = build_parser().parse_args(["status", "--content"])
    assert args.content is True


def test_status_resolve_flag_parses():
    from phoenix.cli import build_parser
    args = build_parser().parse_args(["status", "--resolve"])
    assert args.resolve is True


def test_status_resolve_and_content_combined_parse():
    from phoenix.cli import build_parser
    args = build_parser().parse_args(["status", "--resolve", "--content"])
    assert args.resolve is True
    assert args.content is True


def test_diff_requires_positional_repo():
    from phoenix.cli import build_parser
    args = build_parser().parse_args(["diff", "/tmp/other-machine"])
    assert args.other_repo == "/tmp/other-machine"


def test_diff_without_positional_fails():
    from phoenix.cli import build_parser
    with pytest.raises(SystemExit):
        build_parser().parse_args(["diff"])


def test_rollback_commit_is_optional():
    from phoenix.cli import build_parser
    args = build_parser().parse_args(["rollback"])
    assert args.commit is None


def test_rollback_with_commit_and_yes():
    from phoenix.cli import build_parser
    args = build_parser().parse_args(["rollback", "abc1234", "--yes"])
    assert args.commit == "abc1234"
    assert args.yes is True


def test_reminder_defaults():
    from phoenix.cli import build_parser
    args = build_parser().parse_args(["reminder"])
    assert args.command == "reminder"
    from phoenix.reminder import DEFAULT_THRESHOLD_DAYS
    assert args.days == DEFAULT_THRESHOLD_DAYS
    assert args.quiet is False


def test_reminder_custom_days_and_quiet():
    from phoenix.cli import build_parser
    args = build_parser().parse_args(["reminder", "--days", "14", "--quiet"])
    assert args.days == 14
    assert args.quiet is True


def test_missing_subcommand_fails():
    from phoenix.cli import build_parser
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_unknown_subcommand_fails():
    from phoenix.cli import build_parser
    with pytest.raises(SystemExit):
        build_parser().parse_args(["nimportequoi"])
