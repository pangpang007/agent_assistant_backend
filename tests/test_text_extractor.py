import pytest
import tempfile
from pathlib import Path

from app.services.text_extractor import (
    detect_file_type,
    extract_text,
    validate_file_size,
)


class TestDetectFileType:

    def test_pdf(self):
        assert detect_file_type("report.pdf") == "pdf"

    def test_txt(self):
        assert detect_file_type("notes.txt") == "txt"

    def test_markdown(self):
        assert detect_file_type("readme.md") == "md"
        assert detect_file_type("readme.markdown") == "md"

    def test_csv(self):
        assert detect_file_type("data.csv") == "csv"

    def test_docx(self):
        assert detect_file_type("doc.docx") == "docx"

    def test_unsupported(self):
        assert detect_file_type("image.png") is None
        assert detect_file_type("archive.zip") is None


class TestValidateFileSize:

    def test_valid_size(self):
        validate_file_size(1024, "pdf")  # 不抛异常

    def test_too_large(self):
        with pytest.raises(ValueError):
            validate_file_size(100 * 1024 * 1024, "pdf")  # 100MB > 50MB limit


class TestExtractText:

    def test_extract_txt(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False, encoding="utf-8") as f:
            f.write("Hello, World!\n这是测试文本。")
            f.flush()
            text = extract_text(f.name, "txt")
            assert "Hello, World!" in text
            assert "测试文本" in text

    def test_extract_csv(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False, encoding="utf-8") as f:
            f.write("name,age,city\nAlice,30,NYC\nBob,25,LA")
            f.flush()
            text = extract_text(f.name, "csv")
            assert "Alice" in text
            assert "name" in text

    def test_unsupported_type(self):
        with pytest.raises(ValueError):
            extract_text("/tmp/test.xyz", "xyz")
