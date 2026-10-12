"""The excerpt shown under an answer must contain the words of that answer."""

from app.generation.excerpts import best_excerpt, best_excerpts
from app.retrieval.embedder import HashEmbedder

# How a filled-in PDF form reads once extracted: labels and values on separate lines, no punctuation.
FORM = """2. EMERGENCY CONTACT 3. INSURANCE INFORMATION
CONTACT NAME
Harold Whitfield
INSURANCE PROVIDER
Cascadia Health Partners
PHONE NUMBER
(503) 555-2290
GROUP NUMBER
GRP-6621
4. REASON FOR TODAY'S VISIT
Persistent lower back pain for about three weeks. Also would like to renew my allergy prescription."""

PROSE = (
    "The handbook was revised in January. In 2025, full-time employees are entitled to 24 days of paid "
    "annual leave per calendar year. Unused days expire in March. Requests go through the staff portal."
)


def test_form_values_are_quoted_not_section_headings():
    excerpt = best_excerpt(
        FORM,
        "Who is the emergency contact and what is their number?",
        "Harold Whitfield, (503) 555-2290",
        HashEmbedder(),
    )
    assert "Harold Whitfield" in excerpt
    assert "(503) 555-2290" in excerpt
    assert "allergy prescription" not in excerpt


def test_a_short_form_value_is_shown_with_its_field_label():
    excerpt = best_excerpt(FORM, "Who is the emergency contact?", "Harold Whitfield", HashEmbedder())
    assert excerpt == "CONTACT NAME Harold Whitfield"


def test_a_second_source_shows_the_part_the_first_did_not():
    other_chunk = "Millbrook Falls\nSpouse\n(503) 555-8827\n97045"
    first, second = best_excerpts(
        [FORM, other_chunk], "Who is the emergency contact?", "Harold Whitfield, spouse, (503) 555-2290", HashEmbedder()
    )
    assert "Harold Whitfield" in first and "(503) 555-2290" in first
    assert second == "Spouse", "must not show the other phone number just because it shares an area code"


def test_prose_excerpt_is_the_sentence_that_states_the_answer():
    excerpt = best_excerpt(PROSE, "How many days of annual leave in 2025?", "24 days", HashEmbedder())
    assert excerpt == "In 2025, full-time employees are entitled to 24 days of paid annual leave per calendar year."


def test_a_paraphrased_answer_falls_back_to_the_closest_sentence():
    excerpt = best_excerpt(PROSE, "How many days of annual leave in 2025?", "Zwei Dutzend", HashEmbedder())
    assert excerpt and excerpt in PROSE.replace(". ", ". … ") + " … "
    assert len(excerpt) < len(PROSE)


def test_excerpt_is_capped_in_length_and_sentences():
    text = "\n".join(f"Item {i} costs {i}00 dollars in region {i}" for i in range(1, 30))
    answer = ", ".join(f"{i}00" for i in range(1, 30))
    excerpt = best_excerpt(text, "What do the items cost?", answer, HashEmbedder())
    assert excerpt.count(" … ") <= 2
    assert len(excerpt) <= 400


def test_a_sentence_wrapped_over_pdf_lines_is_quoted_whole():
    wrapped = (
        "The software stack is carefully selected. Python 3.12 serves as the primary programming language, chosen\n"
        "for its extensive support for computer vision libraries. OpenCV 4.5 is utilized for image processing."
    )
    excerpt = best_excerpt(wrapped, "Which language is used?", "Python 3.12", HashEmbedder())
    assert excerpt == (
        "Python 3.12 serves as the primary programming language, chosen "
        "for its extensive support for computer vision libraries."
    )


def test_a_long_excerpt_is_cut_at_a_word_and_marked():
    sentence = "The answer is forty-two " + "and it goes on and on " * 30 + "until the end."
    excerpt = best_excerpt(sentence, "What is the answer?", "forty-two", HashEmbedder())
    assert len(excerpt) <= 402
    assert excerpt.endswith(" …")
