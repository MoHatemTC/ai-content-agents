from src.ingestion.chunker import TextChunker


def test_chunks_do_not_split_words():
    text = (
        "Conduction transfers heat through direct molecular contact. "
        "Convection carries heat in the bulk motion of a fluid. "
        "Radiation transfers energy through electromagnetic waves."
    )

    chunker = TextChunker(chunk_size=60, overlap=10)
    chunks = chunker.chunk(text, "doc")

    for chunk in chunks:
        # chunk should not begin with the second half of a word
        assert not (
            chunk.text
            and chunk.text[0].isalnum()
            and chunk.start_char > 0
            and text[chunk.start_char - 1].isalnum()
        )

        # chunk should not end in the middle of a word
        if chunk.end_char < len(text):
            assert text[chunk.end_char].isspace()

def test_overlap_is_preserved():
    text = (
        "This is sentence one. "
        "This is sentence two. "
        "This is sentence three. "
        "This is sentence four."
    )

    chunker = TextChunker(chunk_size=40, overlap=10)
    chunks = chunker.chunk(text, "doc")

    assert len(chunks) > 1

    first = chunks[0].text
    second = chunks[1].text

    overlap = first[-10:]

    assert overlap in second


def test_long_word_does_not_loop():
    text = "a" * 3000

    chunker = TextChunker(chunk_size=1000, overlap=100)
    chunks = chunker.chunk(text, "doc")

    assert len(chunks) > 0


def test_sentence_split():
    chunker = TextChunker()

    text = (
        "Sentence one. "
        "Sentence two! "
        "Sentence three?"
    )

    spans = chunker._split_sentences(text)

    sentences = [text[s:e] for s, e in spans]

    assert sentences == [
        "Sentence one.",
        "Sentence two!",
        "Sentence three?",
    ]



def test_sentence_packing():
    chunker = TextChunker(chunk_size=40, overlap=10)

    text = (
        "Sentence one. "
        "Sentence two. "
        "Sentence three."
    )

    spans = chunker._pack_sentences(text)

    chunks = [text[s:e] for s, e in spans]

    assert chunks == [
        "Sentence one. Sentence two.",
        "Sentence three.",
    ]


def test_long_sentence_is_split():
    chunker = TextChunker(
        chunk_size=40,
        overlap=10,
    )

    text = (
        "This is one extremely long sentence that should be split into "
        "multiple chunks while preserving complete words throughout."
    )

    spans = chunker._split_long_sentence(
        text,
        0,
        len(text),
    )

    chunks = [text[s:e] for s, e in spans]

    assert len(chunks) > 1

    for start, end in spans:

        if end < len(text):
            assert (
                text[end - 1].isspace()
                or text[end - 1] in ".!?"
            )