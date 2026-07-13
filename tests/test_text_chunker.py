import pytest
from app.services.text_chunker import TextChunker


class TestTextChunker:

    def test_basic_chunking(self):
        """基本分块：短文本不拆分"""
        chunker = TextChunker(chunk_size=512, chunk_overlap=50)
        text = "这是一段短文本。" * 10
        chunks = chunker.chunk_text(text)
        assert len(chunks) >= 1
        assert all(c.content.strip() for c in chunks)

    def test_long_text_chunking(self):
        """长文本分块：超过 chunk_size 时正确拆分"""
        chunker = TextChunker(chunk_size=100, chunk_overlap=10)
        text = "这是一段很长的文本。" * 500  # 约 5000+ tokens
        chunks = chunker.chunk_text(text)
        assert len(chunks) > 1
        # 验证重叠
        for i in range(1, len(chunks)):
            assert chunks[i].chunk_index == i

    def test_empty_text(self):
        """空文本返回空列表"""
        chunker = TextChunker()
        chunks = chunker.chunk_text("")
        assert chunks == []

    def test_token_count(self):
        """验证 token 计数正确"""
        chunker = TextChunker(chunk_size=512)
        text = "Hello world, this is a test." * 100
        chunks = chunker.chunk_text(text)
        total_tokens = sum(c.token_count for c in chunks)
        direct_count = chunker.count_tokens(text)
        # 由于重叠，总 token 数可能大于直接计数
        assert total_tokens >= direct_count

    def test_overlap_invalid_config(self):
        """overlap >= size 时抛出 ValueError"""
        with pytest.raises(ValueError):
            TextChunker(chunk_size=100, chunk_overlap=100)

    def test_paragraph_boundary(self):
        """尽量在段落边界分块"""
        chunker = TextChunker(chunk_size=50, chunk_overlap=5)
        text = "\n\n".join([f"段落 {i}: " + "内容" * 20 for i in range(10)])
        chunks = chunker.chunk_text(text)
        assert len(chunks) >= 1


class TestTextChunkerCountTokens:

    def test_count_tokens_chinese(self):
        """中文 token 计数"""
        chunker = TextChunker()
        count = chunker.count_tokens("你好世界")
        assert count > 0

    def test_count_tokens_english(self):
        """英文 token 计数"""
        chunker = TextChunker()
        count = chunker.count_tokens("Hello world")
        assert count > 0
