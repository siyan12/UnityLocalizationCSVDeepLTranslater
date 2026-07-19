from collections import Counter

import pytest

from translator_core import (
    StructureValidationError,
    detokenize_placeholders,
    tokenize_placeholders,
    validate_translated_structure,
)


ROUND_TRIP_CASES = [
    "Value: %1$s / %s / %02d / %(name)s / %r / %(item)r / %%",
    "Hello {name}, {0:N2}, {value:.2f}, {name!r}",
    "Show {{literal}} and {name}",
    "{count, plural, =0 {No items} one {# item} other {{count} apples}}",
    "{count:plural:{count} item|{count} items}",
    '<color=#ff00ff><b>Hello {name}</b></color><br/><sprite name="coin">',
    "<#ff0000>Danger</color>",
    "First page<page>Second page",
    "{name} met {name}",
    "Line 1\r\nLine 2\n{name} and literal\\nnext",
]


@pytest.mark.parametrize("source", ROUND_TRIP_CASES)
def test_protected_structure_round_trips_exactly(source):
    tokenized, mapping = tokenize_placeholders(source)

    assert detokenize_placeholders(tokenized, mapping) == source
    assert len(mapping) == len(set(mapping))
    assert all(tokenized.count(token) == 1 for token in mapping)


def test_repeated_placeholders_are_counted_individually():
    tokenized, mapping = tokenize_placeholders("{name} met {name}")

    assert Counter(mapping.values())["{name}"] == 2
    assert len(mapping) == 2
    assert tokenized.count("_PH_") == 2


@pytest.mark.parametrize(
    "source",
    [
        "Progress is 100% complete",
        "Save 50% discount today",
        "Battery is 100% full",
    ],
)
def test_natural_percent_phrase_is_not_mistaken_for_printf(source):

    tokenized, mapping = tokenize_placeholders(source)

    assert tokenized == source
    assert mapping == {}


def test_token_prefix_collision_does_not_damage_user_text():
    source = "Debug __UL10N0_PH_0000__ {name}"
    tokenized, mapping = tokenize_placeholders(source)

    assert "__UL10N0_PH_0000__" in tokenized
    assert all(token.startswith("__UL10N1_PH_") for token in mapping)
    assert detokenize_placeholders(tokenized, mapping) == source


@pytest.mark.parametrize("mutation", ["delete", "duplicate", "unknown", "rewrite"])
def test_changed_translation_tokens_are_rejected(mutation):
    tokenized, mapping = tokenize_placeholders("Hello {name}\n")
    first = next(iter(mapping))
    if mutation == "delete":
        translated = tokenized.replace(first, "", 1)
    elif mutation == "duplicate":
        translated = tokenized + first
    elif mutation == "unknown":
        translated = tokenized + first[:-6] + "9999__"
    else:
        translated = tokenized.replace(first, first.replace("PH", "PX"), 1)

    with pytest.raises(StructureValidationError, match="protected"):
        detokenize_placeholders(translated, mapping)


def test_placeholder_reordering_preserves_valid_multiset():
    source = "{first} then {second}"
    tokenized, mapping = tokenize_placeholders(source)
    tokens = list(mapping)
    reordered = tokenized.replace(tokens[0], "TEMP", 1).replace(tokens[1], tokens[0], 1).replace("TEMP", tokens[1], 1)
    translated = detokenize_placeholders(reordered, mapping)

    validate_translated_structure(source, translated)


def test_placeholder_cannot_move_outside_its_rich_text_tag():
    with pytest.raises(StructureValidationError, match="placeholder"):
        validate_translated_structure("<b>{name}</b>", "{name}<b></b>")


@pytest.mark.parametrize(
    ("source", "translated", "message"),
    [
        ("<b><i>x</i></b>", "<b><i>x</b></i>", "tag nesting"),
        ("<b>x</b>", "<b>x", "Unclosed"),
        ("one\r\ntwo", "one\ntwo", "line-break"),
        ("Value {name}", "Value {other}", "placeholder"),
    ],
)
def test_structure_validator_rejects_corruption(source, translated, message):
    with pytest.raises(StructureValidationError, match=message):
        validate_translated_structure(source, translated)


@pytest.mark.parametrize("source", ["Hello {name", "Hello name}", "<b>Hello"])
def test_invalid_source_structure_is_rejected_before_translation(source):
    with pytest.raises(StructureValidationError):
        tokenize_placeholders(source)
