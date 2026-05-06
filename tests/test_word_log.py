import pytest
from src.word_log import (
    log_word, get_week_words, get_all_user_ids,
    upsert_settings, get_settings, set_review_state,
    get_review_state, advance_review, end_review,
    set_onboard_state, get_onboard_state, end_onboarding
)

@pytest.mark.asyncio
async def test_log_and_get_words(test_db):
    user_id = 1
    await log_word(user_id, "Abstain")
    await log_word(user_id, "Benevolent")
    
    words = await get_week_words(user_id)
    assert len(words) == 2
    assert "abstain" in words
    assert "benevolent" in words

@pytest.mark.asyncio
async def test_user_ids(test_db):
    await log_word(1, "hello")
    await log_word(2, "world")
    ids = await get_all_user_ids()
    assert set(ids) == {1, 2}

@pytest.mark.asyncio
async def test_settings_upsert_get(test_db):
    user_id = 99
    # Test default
    settings = await get_settings(user_id)
    assert settings["word_of_day"] == 1
    
    # Test update
    await upsert_settings(user_id, word_of_day=0, audio=1)
    new_settings = await get_settings(user_id)
    assert new_settings["word_of_day"] == 0
    assert new_settings["audio"] == 1

@pytest.mark.asyncio
async def test_review_state(test_db):
    user_id = 55
    words = ["apple", "banana"]
    await set_review_state(user_id, words)
    
    state = await get_review_state(user_id)
    assert state["q_index"] == 0
    assert state["words"] == words
    
    await advance_review(user_id, 1)
    state = await get_review_state(user_id)
    assert state["q_index"] == 1
    
    await end_review(user_id)
    assert await get_review_state(user_id) is None

@pytest.mark.asyncio
async def test_onboarding_state(test_db):
    user_id = 77
    await set_onboard_state(user_id, step=2)
    state = await get_onboard_state(user_id)
    assert state["step"] == 2
    
    await end_onboarding(user_id)
    assert await get_onboard_state(user_id) is None
    settings = await get_settings(user_id)
    assert settings["onboarded"] == 1
