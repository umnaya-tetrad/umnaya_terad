import pytest

from auth import AuthenticationError, hash_password, normalise_username, verify_password


def test_password_is_salted_and_verifiable() -> None:
    first_hash = hash_password("correct horse battery staple")
    second_hash = hash_password("correct horse battery staple")

    assert first_hash != second_hash
    assert "correct horse" not in first_hash
    assert verify_password("correct horse battery staple", first_hash)
    assert not verify_password("wrong password", first_hash)


def test_username_is_normalised_and_checked() -> None:
    assert normalise_username("  Student_01 ") == "student_01"
    with pytest.raises(AuthenticationError):
        normalise_username("no spaces allowed")
