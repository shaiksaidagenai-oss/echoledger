from datetime import date

import pytest

from echoledger.cli import build_parser, cmd_fetch, cmd_show


def test_parse_date_accepts_iso_format() -> None:
    parser = build_parser()
    args = parser.parse_args(["show", "--date", "2026-10-29"])
    assert args.date == date(2026, 10, 29)


def test_parse_date_rejects_bad_format() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["show", "--date", "29-10-2026"])


def test_fetch_command_wires_to_cmd_fetch() -> None:
    parser = build_parser()
    args = parser.parse_args(["fetch", "--date", "2026-10-29"])
    assert args.func is cmd_fetch


def test_show_command_wires_to_cmd_show() -> None:
    parser = build_parser()
    args = parser.parse_args(["show"])
    assert args.func is cmd_show
    assert args.date is None  # defaults to today when not given


def test_a_command_is_required() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])
