from app.knowledge.uploads.text_encoding import normalize_to_utf8


def test_utf8_file_is_left_alone():
    assert normalize_to_utf8("plain café".encode("utf-8"), ".txt") is None


def test_utf16_with_bom_is_converted():
    assert normalize_to_utf8("héllo wörld".encode("utf-16"), ".txt") == "héllo wörld".encode("utf-8")


def test_utf16_without_bom_is_converted():
    assert normalize_to_utf8("retries: 7".encode("utf-16-le"), ".log") == b"retries: 7"


def test_windows_1252_is_converted():
    text = "Café menu – naïve résumé €5"
    assert normalize_to_utf8(text.encode("cp1252"), ".txt") == text.encode("utf-8")


def test_utf8_bom_is_removed():
    assert normalize_to_utf8(b"\xef\xbb\xbf# Title", ".md") == b"# Title"


def test_binary_formats_are_never_touched():
    assert normalize_to_utf8(b"%PDF-1.7 \xff\xfe", ".pdf") is None
    assert normalize_to_utf8(b"\x89PNG\r\n", ".png") is None
