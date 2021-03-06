import pytest


def test_clear_from_build_in_var():
    from akrr.util import clear_from_build_in_var

    tmp = {}
    exec(
        "import sys\n"
        "my_var1=sys.path\n"
        "my_var2=2\n",
        tmp)
    tmp = clear_from_build_in_var(tmp)

    assert "__builtins__" not in tmp
    assert "sys" not in tmp
    assert "my_var1" in tmp
    assert "my_var2" in tmp
    assert tmp["my_var2"] == 2


def test_exec_files_to_dict(datadir):
    from akrr.util import exec_files_to_dict

    tmp = exec_files_to_dict(str(datadir.join("test.py")))

    assert "__builtins__" not in tmp
    assert "sys" not in tmp
    assert "my_path" in tmp
    assert "banana" in tmp
    assert tmp["banana"] == "yellow"


@pytest.mark.parametrize("s, d, keep_double_brackets, expected", [
    (
        "here is fancy test {var1} to replace\n and ${{var1}} to keep",
        {"var1": "var1_value", "var2": "var2_value"},
        None,
        "here is fancy test var1_value to replace\n and ${var1} to keep"
    ), (
        "here is fancy test {var1} to replace\n and ${{var1}} to keep",
        {"var1": "var1_value", "var2": "var2_value"},
        False,
        "here is fancy test var1_value to replace\n and ${var1} to keep"
    ), (
        "here is fancy test {var1} to replace\n and ${{var1}} to keep",
        {"var1": "var1_value", "var2": "var2_value"},
        True,
        "here is fancy test var1_value to replace\n and ${{var1}} to keep"
    ), (
        "here is fancy test {var1} to replace\n and ${{var1}} to keep\n and {var2} is recursive",
        {"var1": "var1_value", "var2": "var2_{var1}_value"},
        None,
        "here is fancy test var1_value to replace\n and ${var1} to keep\n and var2_var1_value_value is recursive"
    )
])
def test_format_recursively(s: str, d: dict, keep_double_brackets: bool, expected: str):
    from akrr.util import format_recursively
    if keep_double_brackets is None:
        assert format_recursively(s, d) == expected
    else:
        assert format_recursively(s, d, keep_double_brackets) == expected


@pytest.mark.parametrize("s, ds, expected", [
    (
        "here is fancy test @var1@ to replace\n and @var2@ to replace too",
        [{"var1": "var1_value", "var2": "var2_value"}, {"var2": "var2_new_value"}],
        "here is fancy test var1_value to replace\n and var2_new_value to replace too"
    ),
])
def test_replace_at_var_at(s, ds, expected):
    from akrr.util import replace_at_var_at
    assert replace_at_var_at(s, ds) == expected


@pytest.mark.parametrize("a, b, tol, result", [
    (0.0, 0.0, None, True),
    (1.0e-8, 0.0, None, True),
    (0.0, 1.0e-8, None, True),
    (1.0e-6, 0.0, None, False),
    (0.0, 1.0e-6, None, False),
    (1234.5678, 1234.5688, None, False),
    (1234.5678, 1234.5679, None, True),
    (1234.56, 1245.56, 1.0e-3, False),
    (1234.56, 1235.56, 1.0e-3, True),
])
def test_floats_are_close(a, b, tol, result):
    from akrr.util import floats_are_close
    if tol is None:
        assert floats_are_close(a, b) == result
    else:
        assert floats_are_close(a, b, tol) == result


@pytest.mark.parametrize("s, result", [
    ("0.0", False),
    ("0", True),
    ("10.0", False),
    ("10", True),
    ("10.20", False),
    ("-10.0", False),
    ("-10", True),
    ("-10.20", False),
    ("10.0a", False),
    ("-1a0", False),
    ("10.20a", False),
])
def test_is_int(s, result):
    from akrr.util import is_int
    assert is_int(s) == result


@pytest.mark.parametrize("s, result", [
    ("0.0", True),
    ("0", True),
    ("10.0", True),
    ("10", True),
    ("10.20", True),
    ("-10.0", True),
    ("-10", True),
    ("-10.20", True),
    ("10.0a", False),
    ("-1a0", False),
    ("10.20a", False),
])
def test_is_float(s, result):
    from akrr.util import is_float
    assert is_float(s) == result


@pytest.mark.parametrize("a, result", [
    ("0.0", 0.0),
    ("0", 0),
    ("10.0", 10.0),
    ("10", 10),
    ("10.20", 10.20),
    ("103", 103)
])
def test_get_float_or_int(a, result):
    from akrr.util import floats_are_close, get_float_or_int

    b = get_float_or_int(a)
    assert type(b) == type(result)
    if isinstance(result, int):
        assert b == result
    elif isinstance(result, float):
        assert floats_are_close(b, result)
    else:
        assert 0
