"""文件存储管理：处理上传文件的存储和清理。"""

import uuid
from pathlib import Path

from app.core.config import settings


def get_upload_dir() -> Path:
    """获取上传文件根目录。"""
    upload_dir = Path(settings.upload_base_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def get_document_storage_path(kb_id: uuid.UUID, filename: str) -> str:
    """
    生成文档存储路径。
    格式: {upload_base_dir}/{kb_id}/{uuid4}_{filename}
    """
    kb_dir = get_upload_dir() / str(kb_id)
    kb_dir.mkdir(parents=True, exist_ok=True)

    safe_name = f"{uuid.uuid4().hex}_{filename}"
    return str(kb_dir / safe_name)


def delete_document_file(file_path: str) -> None:
    """删除文档文件。"""
    path = Path(file_path)
    if path.exists():
        path.unlink()

        parent = path.parent
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()
