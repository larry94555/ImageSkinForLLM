"""Examples when asked (Larry's test on PR #91, 2026-10-15)."""

import logging

import pytest
from test_question_scope import Llm

from imageskin.chat import Conversation
from imageskin.examples import asks_for_example, earlier_question, example_asked, example_of
from imageskin.lookup import Passage, rank


@pytest.mark.parametrize(
    ("prompt", "asks"),
    [
        ("Can you give me an example?", True),
        ("Any examples, please?", True),
        ("Could you illustrate that?", True),
        ("What is a prime, for instance?", True),
        ("What did Euler notice?", False),
    ],
)
def test_a_request_for_an_example_is_recognised(prompt: str, asks: bool) -> None:
    assert asks_for_example(prompt) is asks


def test_what_an_example_is_of_is_what_the_request_says_besides_asking() -> None:
    assert example_of("Can you give an example of a prime number?") == "a prime number"
    assert example_of("What is a prime, for instance?") == "prime"
    assert example_of("Can you give me an example of that?") is None
    assert example_of("Can you give me an example?") is None
    assert example_of("Could you share another simple example, please?") is None
    assert example_of("Let’s see some examples") is None


def test_a_bare_request_is_about_the_last_question_that_said_what_it_was_about() -> None:
    asked = ["What is a prime?", "What did Euler notice?", "Can you give me an example?"]
    assert earlier_question(asked) == "What did Euler notice?"
    assert earlier_question(["Give me an example of the zeta function."]) == "the zeta function"
    assert earlier_question(["Can you give me an example?"]) is None
    assert earlier_question([]) is None


def test_the_llm_is_asked_for_particular_examples_of_the_earlier_question() -> None:
    asked = example_asked("Can you give me an example?", "What did Euler notice?")
    assert asked.startswith("Can you give me an example?\n")
    assert 'examples for the earlier question "What did Euler notice?"' in asked
    assert "Don't only say the idea again" in asked
    assert "examples for what was asked" in example_asked("An example of a prime?", None)


def test_can_you_give_me_an_example_is_answered_about_the_question_before_it(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Larry (2026-10-15): "It failed to provide examples when I asked." """
    looked_up: list[str] = []

    def find(prompt: str) -> list[str]:
        looked_up.append(prompt)
        return ["Euler's Product (a.pdf, page 2): the observation of Euler that the product"]

    llm = Llm()
    conversation = Conversation(llm, lambda: 4096, find=find, content_only=lambda: True)
    conversation.send("What did Euler notice?")
    with caplog.at_level(logging.INFO, logger="imageskin.chat"):
        conversation.send("Can you give me an example?")
        conversation.send("Can you give an example of a prime number?")
    assert looked_up == [
        "What did Euler notice?",
        "What did Euler notice?",
        "a prime number",
    ]
    sent = llm.sent[1][-1]["content"]
    assert "the observation of Euler" in sent
    assert sent.endswith(example_asked("Can you give me an example?", "What did Euler notice?"))
    assert [t.content for t in conversation.turns()][2] == "Can you give me an example?"
    records = [r for r in caplog.records if r.message == "Example asked for"]
    assert [r.about_earlier_question for r in records] == [True, False]  # type: ignore[attr-defined]


def test_a_first_request_for_an_example_is_looked_up_as_it_is() -> None:
    looked_up: list[str] = []

    def find(prompt: str) -> list[str]:
        looked_up.append(prompt)
        return []

    Conversation(Llm(), lambda: 4096, find=find).send("Can you give me an example?")
    assert looked_up == ["Can you give me an example?"]


def test_an_example_of_a_rare_subject_is_found_in_the_content() -> None:
    """Review on PR #91: "give", which the content lacks, outweighed a subject only one
    passage has."""

    def pdf(text: str) -> Passage:
        return Passage("pdf", "p", "a.pdf", "", text, [1])

    plants = [
        pdf("Leaves use photosynthesis."),
        *(pdf(f"Roots drink water {n}.") for n in range(6)),
    ]
    asked = "Can you give an example of photosynthesis?"
    assert rank(asked, plants) == []  # looked up as it is, it isn't found
    subject = example_of(asked)
    assert subject == "photosynthesis"
    assert rank(subject, plants)[0].passage.text == "Leaves use photosynthesis."
