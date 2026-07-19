from resolve_configurator.naming import sanitize_segment


def test_replaces_forbidden_characters():
    assert sanitize_segment("10:00") == "10-00"


def test_distinct_inputs_do_not_collide():
    assert sanitize_segment("10:00") != sanitize_segment("1000")


def test_collapses_whitespace():
    assert sanitize_segment("a   b") == "a b"


def test_trims_whitespace_and_dots():
    assert sanitize_segment("  name.  ") == "name"


def test_blank_becomes_untitled():
    assert sanitize_segment("") == "untitled"
    assert sanitize_segment("   ") == "untitled"


def test_caps_length():
    assert len(sanitize_segment("a" * 500)) == 200


def test_replaces_every_forbidden_character():
    for ch in ["/", "\\", ":", "*", "?", '"', "<", ">", "|"]:
        assert ch not in sanitize_segment(f"a{ch}b")


def test_theatre_with_slash():
    assert sanitize_segment("Globe / Studio") == "Globe - Studio"
