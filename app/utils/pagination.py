def get_offset(page: int, page_size: int) -> int:
    """计算分页 offset"""
    return max(0, (page - 1) * page_size)


def has_next_page(total: int, page: int, page_size: int) -> bool:
    """判断是否还有下一页"""
    return page * page_size < total
