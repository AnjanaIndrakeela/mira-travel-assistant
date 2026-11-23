"""Password hashing (scrypt, standard library)."""

import pytest

from app.core.security import hash_password, verify_password


def test_hash_and_verify():
    h = hash_password("correct horse")
    assert h.startswith("scrypt$") and "correct horse" not in h
    assert verify_password("correct horse", h)
    assert not verify_password("wrong horse", h)


def test_same_password_gets_a_new_salt():
    assert hash_password("pw") != hash_password("pw")


@pytest.mark.parametrize("stored", ["", "plain", "md5$x$y", "scrypt$1$2$3$zz$yy"])
def test_bad_stored_values_never_verify(stored):
    assert verify_password("pw", stored) is False


def test_empty_password_rejected():
    with pytest.raises(ValueError):
        hash_password("")
