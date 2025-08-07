def split_text_into_chunks(text, max_length=4000):
    """
    Teilt einen Text in mehrere Blöcke auf, ohne Wörter zu zerschneiden.
    Standard: 4000 Zeichen pro Block (Discord Embed Limit = 4096).
    """
    paragraphs = text.split("\n\n")  # Absätze trennen
    chunks = []
    current_chunk = ""

    for para in paragraphs:
        if len(current_chunk) + len(para) + 2 < max_length:
            current_chunk += para + "\n\n"
        else:
            chunks.append(current_chunk.strip())
            current_chunk = para + "\n\n"

    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks
