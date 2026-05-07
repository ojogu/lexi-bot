import pytest
from src.lexi import detect_intent, _parse_question, _parse_grade, grade_answer

@pytest.mark.asyncio
async def test_detect_intent(mocker):
    # Mock litellm.acompletion
    mock_completion = mocker.patch("litellm.acompletion")
    mock_completion.return_value.choices[0].message.content = "  SPELLING  "
    
    intent = await detect_intent("How do you spel this?")
    assert intent == "SPELLING"

def test_parse_question():
    raw = (
        "TYPE: fill-in-the-blank\n"
        "WORD: ephemeral\n"
        "QUESTION: Life is [___].\n"
        "A. short\n"
        "B. long\n"
        "ANSWER: A\n"
        "EXPLANATION: Because it ends."
    )
    q = _parse_question(raw)
    assert q["type"] == "fill-in-the-blank"
    assert q["word"] == "ephemeral"
    assert "Life is [___]." in q["question"]
    assert "A. short" in q["question"]
    assert q["answer"] == "A"
    assert q["explanation"] == "Because it ends."

def test_parse_grade():
    raw = "RESULT: CORRECT\nFEEDBACK: Well done!"
    g = _parse_grade(raw)
    assert g["result"] == "CORRECT"
    assert g["feedback"] == "Well done!"

def test_grade_answer():
    # True/False
    assert grade_answer("test", "True", "true")["correct"] is True
    assert grade_answer("test", "True", "f")["correct"] is False
    
    # Text
    assert grade_answer("ephemeral", "Short-lived", "Short-lived")["correct"] is True
    assert grade_answer("ephemeral", "Short-lived", "permanent")["correct"] is False
