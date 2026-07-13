"""
文本分块器：使用 tiktoken 按 token 数分块。
支持配置 chunk_size 和 chunk_overlap。
"""

from typing import NamedTuple

import structlog
import tiktoken

logger = structlog.get_logger()


class ChunkResult(NamedTuple):
    """分块结果"""
    content: str        # 块的文本内容
    chunk_index: int    # 块序号（从 0 开始）
    token_count: int    # 该块的 token 数


class TextChunker:
    """
    基于 tiktoken 的文本分块器。

    分块策略：
    1. 使用指定的 encoding 模型进行 token 计数
    2. 按 chunk_size（token 数）切分文本
    3. 相邻块之间保留 chunk_overlap 个 token 的重叠
    4. 尽量在段落/句子边界切分（避免从单词中间断开）
    """

    # tiktoken encoding 名称映射
    ENCODING_MAP = {
        "text-embedding-3-small": "cl100k_base",
        "text-embedding-3-large": "cl100k_base",
        "text-embedding-ada-002": "cl100k_base",
    }

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        embedding_model: str = "text-embedding-3-small",
    ):
        """
        Args:
            chunk_size: 每个块的目标 token 数
            chunk_overlap: 相邻块之间的重叠 token 数
            embedding_model: embedding 模型名称，用于确定 encoding
        """
        if chunk_overlap >= chunk_size:
            raise ValueError(
                f"chunk_overlap ({chunk_overlap}) 必须小于 chunk_size ({chunk_size})"
            )

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        # 获取 tiktoken encoding
        encoding_name = self.ENCODING_MAP.get(embedding_model, "cl100k_base")
        try:
            self.encoding = tiktoken.get_encoding(encoding_name)
        except Exception:
            logger.warning(
                "tiktoken_encoding_not_found, fallback_to_cl100k_base",
                embedding_model=embedding_model,
            )
            self.encoding = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, text: str) -> int:
        """计算文本的 token 数。"""
        return len(self.encoding.encode(text))

    def chunk_text(self, text: str) -> list[ChunkResult]:
        """
        将文本分块。

        算法：
        1. 先将文本按段落分割为段落列表
        2. 使用贪心策略，将段落逐步合并到当前块中
        3. 当当前块的 token 数超过 chunk_size 时，开始新块
        4. 如果单个段落超过 chunk_size，使用 token 级切分
        5. 相邻块保留 chunk_overlap 个 token 的重叠

        Returns:
            ChunkResult 列表
        """
        if not text.strip():
            return []

        # 第一步：按段落分割
        paragraphs = self._split_into_paragraphs(text)

        # 第二步：贪心合并段落为块
        raw_chunks = self._merge_paragraphs(paragraphs)

        # 第三步：添加重叠
        chunks_with_overlap = self._add_overlap(raw_chunks)

        # 第四步：构造结果
        results = []
        for idx, chunk_content in enumerate(chunks_with_overlap):
            token_count = self.count_tokens(chunk_content)
            if token_count > 0:
                results.append(ChunkResult(
                    content=chunk_content.strip(),
                    chunk_index=idx,
                    token_count=token_count,
                ))

        logger.info(
            "text_chunked",
            total_tokens=sum(c.token_count for c in results),
            chunk_count=len(results),
        )

        return results

    def _split_into_paragraphs(self, text: str) -> list[str]:
        """
        将文本按段落分割。
        段落之间以双换行分隔。
        """
        paragraphs = text.split("\n\n")
        return [p.strip() for p in paragraphs if p.strip()]

    def _merge_paragraphs(self, paragraphs: list[str]) -> list[str]:
        """
        贪心合并段落为块。
        每个块的 token 数不超过 chunk_size。
        """
        if not paragraphs:
            return []

        chunks = []
        current_chunk_parts = []
        current_token_count = 0

        for para in paragraphs:
            para_tokens = self.count_tokens(para)

            if para_tokens > self.chunk_size:
                # 单个段落超过 chunk_size，需要先存入当前块，再 token 级切分段落
                if current_chunk_parts:
                    chunks.append("\n\n".join(current_chunk_parts))
                    current_chunk_parts = []
                    current_token_count = 0

                # Token 级切分超长段落
                sub_chunks = self._split_long_text(para)
                chunks.extend(sub_chunks)
                continue

            if current_token_count + para_tokens > self.chunk_size:
                # 当前块已满，存入结果并开始新块
                chunks.append("\n\n".join(current_chunk_parts))
                current_chunk_parts = [para]
                current_token_count = para_tokens
            else:
                # 追加到当前块
                current_chunk_parts.append(para)
                current_token_count += para_tokens

        # 最后一个块
        if current_chunk_parts:
            chunks.append("\n\n".join(current_chunk_parts))

        return chunks

    def _split_long_text(self, text: str) -> list[str]:
        """
        Token 级切分超长文本。
        按 token 数切分，尽量在句子边界断开。
        """
        tokens = self.encoding.encode(text)
        chunks = []
        start = 0

        while start < len(tokens):
            end = start + self.chunk_size

            # 尝试在句子边界切分
            if end < len(tokens):
                # 从 end 位置往回找句子边界（. ! ? \n）
                boundary = self._find_sentence_boundary(tokens, start, end)
                if boundary > start:
                    end = boundary

            chunk_tokens = tokens[start:end]
            chunk_text = self.encoding.decode(chunk_tokens)
            chunks.append(chunk_text.strip())

            start = end

        return [c for c in chunks if c]

    def _find_sentence_boundary(
        self, tokens: list[int], start: int, end: int
    ) -> int:
        """
        在 tokens[start:end] 范围内查找最后一个句子边界。
        句子边界标记：. ! ? 后跟空格或结尾。
        返回句子边界处的 token 索引（不含边界 token）。
        如果找不到句子边界，返回 end。
        """
        # 解码 end 附近的文本，查找句子边界
        search_range = max(start, end - 50)  # 搜索最后 50 个 token
        search_tokens = tokens[search_range:end]
        search_text = self.encoding.decode(search_tokens)

        # 查找最后一个句子结束符
        for marker in [".\n", "!\n", "?\n", ". ", "! ", "? "]:
            last_pos = search_text.rfind(marker)
            if last_pos > 0:
                # 计算对应的 token 位置
                prefix_text = search_text[: last_pos + len(marker)]
                prefix_tokens = self.encoding.encode(prefix_text)
                boundary = search_range + len(prefix_tokens)
                if boundary > start:
                    return boundary

        return end

    def _add_overlap(self, chunks: list[str]) -> list[str]:
        """
        为相邻块添加重叠。
        后一个块的开头 overlap_tokens 个 token 与前一个块的末尾相同。
        """
        if len(chunks) <= 1:
            return chunks

        result = [chunks[0]]

        for i in range(1, len(chunks)):
            prev_text = chunks[i - 1]
            curr_text = chunks[i]

            # 获取前一个块末尾的 overlap 个 token
            prev_tokens = self.encoding.encode(prev_text)
            overlap_tokens = prev_tokens[-self.chunk_overlap:] if len(prev_tokens) >= self.chunk_overlap else prev_tokens

            if overlap_tokens:
                overlap_text = self.encoding.decode(overlap_tokens)
                # 将重叠文本添加到当前块的开头
                result.append(overlap_text.strip() + "\n" + curr_text)
            else:
                result.append(curr_text)

        return result
