import pytest
from src.handlers import start, handle_callback, handle_message
from src.word_log import get_onboard_state, get_settings
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_start_command(test_db, mock_update, mock_context):
    await start(mock_update, mock_context)
    
    # Check if onboarding state was set
    state = await get_onboard_state(mock_update.effective_user.id)
    assert state["step"] == 0
    
    # Check if welcome message was sent
    assert mock_update.message.reply_text.called
    args, kwargs = mock_update.message.reply_text.call_args
    assert "Lexi" in args[0]

@pytest.mark.asyncio
async def test_onboarding_callback(test_db, mock_update, mock_context, mocker):
    user_id = mock_update.effective_user.id
    from src.word_log import set_onboard_state
    await set_onboard_state(user_id, step=0)
    
    # Mock update object for callback
    query = AsyncMock()
    query.from_user.id = user_id
    query.data = "ob_wod_1"
    query.message.chat_id = user_id
    mock_update.callback_query = query
    
    await handle_callback(mock_update, mock_context)
    
    # Check if setting was updated
    settings = await get_settings(user_id)
    assert settings["word_of_day"] == 1
    
    # Check if step advanced
    state = await get_onboard_state(user_id)
    assert state["step"] == 1

@pytest.mark.asyncio
async def test_handle_message_routing(test_db, mock_update, mock_context, mocker):
    # Mock intent detection to return SPELLING
    mocker.patch("src.handlers.detect_intent", return_value="SPELLING")
    mocker.patch("src.handlers.fix_spelling", return_value="Fixed spelling result")
    mocker.patch("src.handlers.get_onboard_state", return_value=None)
    
    await handle_message(mock_update, mock_context)
    
    # Ensure it replied with the fixed spelling
    mock_update.message.reply_text.assert_any_call("Fixed spelling result", parse_mode="HTML")
