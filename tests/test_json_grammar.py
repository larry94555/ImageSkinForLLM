import pytest

from imageskin.json_grammar import compact_grammar
from imageskin.wiki import TOPICS_SCHEMA
from imageskin.wiki_outline import DETAIL_SCHEMA, PARTS_SCHEMA, SECTIONS_SCHEMA, SUMMARY_SCHEMA


def test_a_schema_becomes_a_grammar_for_its_json_with_no_line_breaks() -> None:
    schema = {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "parts": {"type": "array", "items": {"type": "integer"}},
        },
        "required": ["summary", "parts"],
    }
    lines = compact_grammar(schema).splitlines()
    assert lines[0] == "root ::= value4"
    assert lines[4:] == [
        'value3 ::= "[" (integer ("," " "? integer)*)? "]"',
        'value4 ::= "{" "\\"summary\\":" " "? string "," " "? "\\"parts\\":" " "? value3 "}"',
    ]
    # Only a space after a colon or comma is allowed between the values; never a line break.
    assert "space" not in "".join(lines[4:])


def test_objects_in_a_list_may_be_on_lines_of_their_own() -> None:
    """Held to one line, the LLM ends a list of topics after the first (R98)."""
    item = {"type": "object", "properties": {"t": {"type": "string"}}, "required": ["t"]}
    schema = {"type": "object", "properties": {"a": {"type": "array", "items": item}}}
    schema["required"] = ["a"]
    lines = compact_grammar(schema).splitlines()
    assert 'value4 ::= "[" space (value3 ("," space value3)*)? space "]"' in lines
    assert 'value3 ::= "{" "\\"t\\":" " "? string "}"' in lines


def test_every_wiki_schema_is_covered() -> None:
    for schema in (TOPICS_SCHEMA, SECTIONS_SCHEMA, SUMMARY_SCHEMA, DETAIL_SCHEMA, PARTS_SCHEMA):
        assert compact_grammar(schema).startswith("root ::= value")


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "number"},
        {"type": "object", "properties": {"a": {"type": "string"}}},  # "a" not required
        {"type": "object", "properties": {}, "required": []},
    ],
)
def test_a_schema_it_does_not_cover_is_refused(schema: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        compact_grammar(schema)
