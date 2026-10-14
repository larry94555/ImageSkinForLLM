"""What the person can talk about (roadmap R41f, items 52 and 53).

The topics are the wiki's main entries: the first level of each PDF's table of contents (R37a),
with the user's edits (R38), in the order the PDFs and their entries come. A question asking what
can be talked about is recognized from a short list of phrasings, so it costs no LLM call and is
never declined by R41; it is answered from the topics in a short reply made here. A prompt R41
declines names a few of them. Pure Python, no logging: the chat logs.
"""

import random
import re
from collections.abc import Callable, Sequence
from typing import Any

# Questions asking what can be talked about, matched against the whole prompt once it is in lower
# case with its punctuation and a few lead-in and closing words taken off. Each must be the whole
# question, so "What do you know about volcanoes?" is a question about volcanoes, not this.
_ASKING = "(can|could|do|would|will) (you|i|we)|are you able to|is it ok to"
_ABOUT = "(about|on|with|for)"
TOPIC_QUESTIONS = [
    re.compile(p)
    for p in (
        # "What topics can you talk about?", "What can you tell me about?", "Which subjects
        # do you cover?", "What can I ask you about?", "What can I ask?"
        rf"(what|which) ((topics|subjects|things|areas)( do| can)? )?({_ASKING})"
        rf" (talk|tell( me)?|teach( me)?|speak|answer( questions)?|help( me)?|cover|discuss"
        rf"|ask( you)?( questions)?|know|explain)( {_ABOUT})?",
        # "What do you know about?", "What do you know?"
        rf"what (do|did) you (know|cover)( {_ABOUT})?",
        # "What are your topics?", "What topics are there?", "What topics do you have?"
        r"what (are|is) (your|the) (topics|subjects)",
        r"(what|which) (topics|subjects) (are there|do you have|are covered|have you got)",
        # "What are you able to talk about?"
        r"what are you able to (talk|tell me|teach me|answer questions)( about)?",
        # "Topics?", "List your topics"
        r"((list|tell me|show me|give me) )?(your|the) topics( please)?|topics",
    )
]
_LEAD_IN = re.compile(r"^((so|ok|okay|and|hi|hello|hey|well|then|um|please)\b,? ?)+")
_CLOSING = re.compile(r"( (please|today|here|then|exactly|again))+$")
_PUNCTUATION = re.compile(r"[^\w\s']+")

# The most topics named in a reply; it is spoken, so a long list is cut short.
SPOKEN_TOPICS = 8
# Topics named when a prompt is declined.
DECLINE_TOPICS = 3

NO_CONTENT = "I can talk about anything you like. Ask me whatever you want to know."
ONLY_THESE = "I can only answer questions about these topics."
# While a PDF added is still being read or its wiki built, the topics so far aren't all of them
# (review on PR #85).
STILL_READING = "I'm still reading the material I was given, so I can't say what's in it yet."
STILL_READING_REST = "I'm still reading the rest of the material I was given."
ASK_AGAIN = "Ask me again in a little while."
ASK_AGAIN_FOR_ALL = "Ask me again in a little while to hear all of it."
# PDFs were added, but no wiki could be built from them.
NO_TOPICS = "I couldn't work out the topics in the material I was given."
ASK_ABOUT_IT = "Ask me about something in it."
OFF_TOPIC_START = "Sorry, I can only answer questions about the material I was given."
# Choose one topic to suggest, and a few to name when declining. Random by default, so the
# suggestion changes; tests pass their own.
Choose = Callable[[Sequence[str]], str]
Sample = Callable[[Sequence[str], int], list[str]]


def asks_for_topics(prompt: str) -> bool:
    """Whether the prompt asks what can be talked about."""
    text = _PUNCTUATION.sub(" ", prompt.lower().replace("’", "'"))
    text = " ".join(text.split())
    text = _CLOSING.sub("", _LEAD_IN.sub("", text)).strip()
    return any(p.fullmatch(text) for p in TOPIC_QUESTIONS)


def main_entries(contents: list[dict[str, Any]]) -> list[str]:
    """The topics: each PDF's first-level entries' titles, as the wiki shows them (with the
    user's edits), the same title only once."""
    seen: set[str] = set()
    titles = []
    for pdf in contents:
        for entry in pdf["entries"]:
            title = " ".join(str(entry["title"]).split())
            if title and title.casefold() not in seen:
                seen.add(title.casefold())
                titles.append(title)
    return titles


def spoken_list(items: Sequence[str], last: str = "and") -> str:
    """A list said aloud: "A", "A and B" or "A, B and C"."""
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} {last} {items[-1]}"


def listed(topics: list[str]) -> str:
    """The topics said aloud, up to SPOKEN_TOPICS of them, then how many more there are."""
    named = topics[:SPOKEN_TOPICS]
    more = len(topics) - len(named)
    return spoken_list([*named, f"{more} more on the Wiki page"] if more else named)


def topics_reply(
    topics: list[str], content_only: bool, complete: bool = True, choose: Choose | None = None
) -> list[str]:
    """The answer to "What can you talk about?", as its sentences: the topics, that nothing else
    is answered when general prompts are off (R41), and one to ask about. Before any PDF is
    added it can talk about anything. While a PDF is still being read or its wiki built
    (`complete` false), the topics so far are given as only those so far, and it says to ask
    again."""
    if not complete:
        if not topics:
            return [STILL_READING, ASK_AGAIN]
        return [f"So far I can talk about {listed(topics)}.", STILL_READING_REST, ASK_AGAIN_FOR_ALL]
    if not topics:
        return [NO_TOPICS, ASK_ABOUT_IT] if content_only else [NO_CONTENT]
    sentences = [f"I can talk about {listed(topics)}."]
    if content_only:
        sentences.append(ONLY_THESE)
    if len(topics) == 1:
        sentences.append("Ask me anything about it.")
    else:
        sentences.append(f"You could start by asking me about {(choose or random.choice)(topics)}.")
    return sentences


def decline_reply(topics: list[str], sample: Sample | None = None) -> list[str]:
    """What is said when a prompt is declined (R41): sorry, and a few of the topics it can
    answer questions about instead."""
    if not topics:
        return [OFF_TOPIC_START, "Try asking about something in it."]
    named = topics
    if len(topics) > DECLINE_TOPICS:
        named = (sample or random.sample)(topics, DECLINE_TOPICS)
    return [OFF_TOPIC_START, f"You could ask me about {spoken_list(named, 'or')}."]
