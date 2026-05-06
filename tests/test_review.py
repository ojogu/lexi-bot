import pytest
import json
from src.review import handle_review_answer, _format_question
from src.word_log import set_review_state, get_review_state
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_handle_review_navigation(test_db, mock_bot, mocker):
    user_id = 123
    words = ["word1", "word2"]
    await set_review_state(user_id, words)
    
    # Mock _cache_question and send_next_question to avoid side effects
    mocker.patch("src.review._cache_question", new_callable=AsyncMock)
    mocker.patch("src.review.send_next_question", new_callable=AsyncMock)
    
    # Test "next"
    handled = await handle_review_answer(user_id, mock_bot, user_id, "next")
    assert handled is True
    state = await get_review_state(user_id)
    assert state["q_index"] == 1
    
    # Test "previous"
    handled = await handle_review_answer(user_id, mock_bot, user_id, "previous")
    assert handled is True
    state = await get_review_state(user_id)
    assert state["q_index"] == 0

def test_format_question():
    q = {
        "type": "true-or-false",
        "word": "test",
        "question": "Is this a test?"
    }
    formatted = _format_question(q, 1, 10)
    assert "Question 1 of 10" in formatted
    assert "Test" in formatted
    assert "True or False?" in formatted
