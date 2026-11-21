from datetime import date

from app.core.config import Settings


def test_default_today_is_eval_date():
    assert Settings(_env_file=None).mira_today == date(2026, 11, 19)


def test_today_is_configurable(monkeypatch):
    monkeypatch.setenv("MIRA_TODAY", "2027-01-05")
    assert Settings(_env_file=None).mira_today == date(2027, 1, 5)


def test_dataset_dir_exists():
    s = Settings(_env_file=None)
    assert (s.mira_dataset_dir / "rates" / "rate_sheet_2026-27.xlsx").is_file()


def test_empty_margin_override_means_none(monkeypatch):
    monkeypatch.setenv("MIRA_MARGIN_DAY", "")
    assert Settings(_env_file=None).mira_margin_day is None
