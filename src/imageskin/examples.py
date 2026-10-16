"""Examples when asked (Larry's test on PR #91, 2026-10-15): "Can you give me an example?" right
after a question about Euler was looked up on its own, so it found a passage that happens to
say "for example" or nothing at all, and "Give me an example of what Euler noticed" was
answered by saying again what he noticed. A request for an example is looked up by what it is
an example of (the question before it, when it doesn't say), and the LLM is told to give one."""

import re

# A prompt asking for an example says one of these.
_EXAMPLE = re.compile(r"\b(?:examples?|for instance|instances?|illustrat\w*)\b", re.IGNORECASE)
_WORD = re.compile(r"[a-z]+")
_MARKS = " ,;:?.!\"'’"
# "… an example of prime numbers": what follows says what it is an example of.
_OF = re.compile(r"\s*(?:of|about|for|on|from|with)\s+(.+)", re.IGNORECASE | re.DOTALL)
# The words of asking for an example that say nothing about what it is an example of.
_ASKING = frozenset(
    """a an another any are can could do does few for give good have i is it just let me more
    my need of one or other please provide real s share show simple some that the there this
    to two us want what which with would you your concrete easy life like see hear tell""".split()
)


def example_asked(prompt: str, earlier: str | None) -> str:
    """What the LLM is asked for the prompt, which the conversation keeps as typed. A small LLM
    given only "Can you give me an example?" says its last answer again, so the question it
    is about is named."""
    of = f'the earlier question "{earlier}"' if earlier else "what was asked"
    return (
        f"{prompt}\nGive one or two concrete examples for {of}. Each example must be something"
        " particular (numbers, a case, a thing), the reference text's own when it has one, or"
        " else a simple one that fits it, with a sentence on how it shows the idea. Don't only"
        " say the idea again, and don't repeat an example already given."
    )


def asks_for_example(prompt: str) -> bool:
    return _EXAMPLE.search(prompt) is not None


def example_of(prompt: str) -> str | None:
    """What the prompt asks for an example of, without the asking ("a prime number" in "Can you
    give an example of a prime number?"), or None when it doesn't say ("Can you give me an
    example?") and so is about the question before it. Only the subject is looked up: a word
    of asking the content lacks ("give") would outweigh a rare subject (review on PR #91)."""
    found = _EXAMPLE.search(prompt)
    said = _OF.match(prompt[found.end() :]) if found else None
    if said:
        subject = said.group(1)
    else:
        kept = (w.strip(_MARKS) for w in _EXAMPLE.sub(" ", prompt).split())
        subject = " ".join(w for w in kept if w.lower() not in _ASKING)
    subject = subject.strip(" ?.!")
    if all(w in _ASKING for w in _WORD.findall(subject.lower().replace("’", "'"))):
        return None
    return " ".join(subject.split())


def earlier_question(prompts: list[str]) -> str | None:
    """The latest of the earlier prompts that says what it is about, for "another example"."""
    for prompt in reversed(prompts):
        if not asks_for_example(prompt):
            return prompt
        about = example_of(prompt)
        if about is not None:
            return about
    return None
