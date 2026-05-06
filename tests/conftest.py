import pytest
import asyncio
import os

# Set dummy env vars before anything imports src.config
os.environ["TELEGRAM_TOKEN"] = "dummy_token"
os.environ["API_KEY"] = "dummy_api_key"
os.environ["ELEVENLABS_API_KEY"] = "dummy_tts_key"
os.environ["ELEVENLABS_VOICE_ID"] = "dummy_voice_id"

import aiosqlite
from unittest.mock import AsyncMock, MagicMock

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(autouse=True)
async def test_db(monkeypatch, tmp_path):
    """Setup a temporary database for each test."""
    db_file = tmp_path / "test_lexi.db"
    monkeypatch.setattr("src.word_log.DB_PATH", str(db_file))
    monkeypatch.setattr("src.review.DB_PATH", str(db_file))
    
    # Initialize the database schema
    from src.word_log import init_db
    await init_db()
    
    yield db_file
    
    if db_file.exists():
        os.remove(db_file)

@pytest.fixture
def mock_bot():
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    bot.reply_text = AsyncMock()
    return bot

@pytest.fixture
def mock_update():
    update = MagicMock()
    update.effective_user.id = 12345
    update.effective_user.first_name = "TestUser"
    update.effective_chat.id = 12345
    update.message.reply_text = AsyncMock()
    update.message.text = "test message"
    return update

@pytest.fixture
def mock_context():
    context = MagicMock()
    context.bot = AsyncMock()
    return context
