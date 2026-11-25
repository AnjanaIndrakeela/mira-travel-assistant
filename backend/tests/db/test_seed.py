"""Steps 5.10-5.11: seeding is idempotent; passwords are hashed; media rows match the files."""

from pydantic import SecretStr
from sqlalchemy import func, select

from app.core.config import Settings
from app.core.security import verify_password
from app.db.models import Media, User
from app.db.seed import seed


def _settings(staff_pw="staff-test-pw"):
    return Settings(mira_staff_email="staff@seed.example", mira_approver_email="approver@seed.example",
                    mira_staff_password=SecretStr(staff_pw),
                    mira_approver_password=SecretStr("approver-test-pw"))


def _seed_users(db):
    return db.scalars(select(User).where(User.email.like("%@seed.example"))).all()


def test_seed_twice_gives_exactly_two_users(db):
    first = seed(db, _settings())
    second = seed(db, _settings())
    users = _seed_users(db)
    assert sorted(u.role for u in users) == ["approver", "staff"]
    assert sorted(first.users_created) == ["approver", "staff"] and second.users_created == []


def test_passwords_are_hashed(db):
    seed(db, _settings())
    staff = next(u for u in _seed_users(db) if u.role == "staff")
    assert "staff-test-pw" not in staff.password_hash
    assert staff.password_hash.startswith("scrypt$")
    assert verify_password("staff-test-pw", staff.password_hash)
    assert not verify_password("wrong", staff.password_hash)


def test_no_password_means_no_account(db):
    s = Settings(mira_staff_email="nopw@seed.example", mira_approver_email="nopw2@seed.example",
                 mira_staff_password=None, mira_approver_password=None)
    report = seed(db, s)
    assert report.users_created == [] and sorted(report.users_skipped) == ["approver", "staff"]
    assert _seed_users(db) == []


def test_existing_user_is_never_overwritten(db):
    seed(db, _settings())
    before = next(u for u in _seed_users(db) if u.role == "staff").password_hash
    seed(db, _settings(staff_pw="another-pw"))           # a changed .env doesn't reset accounts
    after = next(u for u in _seed_users(db) if u.role == "staff").password_hash
    assert after == before and verify_password("staff-test-pw", after)


def test_media_seeded_once_and_files_exist(db):
    settings = _settings()
    seed(db, settings)
    seed(db, settings)
    rows = db.scalars(select(Media).where(Media.tag == "ella")).all()
    assert len(rows) == 6                                  # 4 illustrations + 2 open-licence photos
    assert db.scalar(select(func.count()).select_from(Media).where(Media.path.like("ella/%"))) == 6
    for row in rows:
        assert (settings.mira_media_dir / row.path).is_file()
        if row.kind == "photo":                            # the licence needs the credit shown
            assert row.credit and row.licence and row.source.startswith("https://commons.wikimedia.org/")
        else:
            assert row.alt.startswith("Illustration") and row.credit is None
