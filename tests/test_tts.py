from src.tts import extract_word

def test_extract_word():
    assert extract_word("what's a subnet") == "subnet"
    assert extract_word("define ephemeral") == "ephemeral"
    assert extract_word("meaning of life") == "life"
    assert extract_word("explain the word volatile") == "the word volatile"
    assert extract_word("subnet") == "subnet"
