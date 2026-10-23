"""Compact JSON, as a grammar llama-server holds its answer to (roadmap R98).

Given a JSON schema, llama-server lets the LLM set its answer out over many lines, and Gemma
always does, with one paragraph number a line: the spaces and line breaks were a fifth of what it
wrote for the wiki's topics and two fifths for its outline, and it writes about 4 tokens a second
on the hosted machine. Asked in words for JSON on one line, it still sets it out (tried on the
sample PDF). So the wiki's schemas are turned into a grammar in llama.cpp's GBNF that keeps each
object and each list of numbers on one line, with at most a space after a colon or comma. Only
between the objects of a list may it break the line: held to one line there too, it ends a list
of topics after the first. Only what the wiki's schemas use is covered: objects whose properties
are all required, arrays, strings and integers.
"""

import json
from typing import Any

# A JSON string, integer and the room between values, as llama.cpp's own grammar for a schema
# has them.
STRING = r'"\"" ( [^"\\\x7F\x00-\x1F] | "\\" (["\\/bfnrt] | "u" [0-9a-fA-F]{4}) )* "\""'
INTEGER = '"-"? ([0-9] | [1-9] [0-9]{0,15})'
SPACE = '| " " | "\\n"{1,2} [ \\t]{0,20}'


def compact_grammar(schema: dict[str, Any]) -> str:
    """The GBNF grammar for the schema's JSON, with line breaks only between the objects of a
    list. ValueError for a schema it doesn't cover."""
    rules: dict[str, str] = {"string": STRING, "integer": INTEGER, "space": SPACE}
    root = rule(schema, rules)
    return "\n".join([f"root ::= {root}", *(f"{name} ::= {body}" for name, body in rules.items())])


def rule(schema: dict[str, Any], rules: dict[str, str]) -> str:
    """The name of the rule for a value of the schema, adding the rules it needs."""
    kind = schema.get("type")
    if kind in ("string", "integer"):
        return kind
    if kind == "array":
        item = rule(schema["items"], rules)
        if schema["items"].get("type") != "object":
            return add(rules, f'"[" ({item} ("," " "? {item})*)? "]"')
        # Between objects the LLM may break the line as it likes: held to one line there, it
        # ends a list of topics after the first (tried on the sample PDF).
        return add(rules, f'"[" space ({item} ("," space {item})*)? space "]"')
    if kind == "object":
        properties: dict[str, Any] = schema.get("properties", {})
        if not properties or set(schema.get("required", [])) != set(properties):
            raise ValueError("Only objects whose properties are all required are covered")
        fields = [
            f'{literal(json.dumps(name) + ":")} " "? {rule(value, rules)}'
            for name, value in properties.items()
        ]
        return add(rules, '"{" ' + ' "," " "? '.join(fields) + ' "}"')
    raise ValueError(f"A schema of type {kind!r} is not covered")


def add(rules: dict[str, str], body: str) -> str:
    name = f"value{len(rules)}"
    rules[name] = body
    return name


def literal(text: str) -> str:
    """Text as a GBNF literal."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
