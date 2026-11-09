import pytest

from imessage_mcp.phones import PhoneError, normalize, try_normalize


@pytest.mark.parametrize(
    "raw",
    [
        "8015550142",
        "18015550142",
        "+18015550142",
        "(801) 555-0142",
        "801.555.0142",
        "801-555-0142",
        "1 (801) 555-0142",
        "+1 801 555 0142",
        " 801 555 0142 ",
    ],
)
def test_accepts_common_us_formats(raw):
    assert normalize(raw) == "+18015550142"


@pytest.mark.parametrize(
    "raw",
    [
        "+442071838750",      # international
        "+8015550142",        # + with only 10 digits
        "28015550142",        # 11 digits not starting with 1
        "55555",              # short code
        "801555014",          # 9 digits
        "180155501423",       # 12 digits
        "priya@example.com",  # email
        "",
        "801-555-O142",       # letter O
        "801/555/0142",       # slash isn't a stripped separator
        "８０１５５５０１４２",  # full-width digits
    ],
)
def test_rejects_everything_else_naming_the_input(raw):
    with pytest.raises(PhoneError) as e:
        normalize(raw)
    assert repr(raw) in str(e.value)


def test_rejects_non_strings():
    with pytest.raises(PhoneError):
        normalize(8015550142)


def test_try_normalize():
    assert try_normalize("801 555 0142") == "+18015550142"
    assert try_normalize("priya@example.com") is None
