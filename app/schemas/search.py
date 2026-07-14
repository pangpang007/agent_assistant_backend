from pydantic import BaseModel


class SearchResultItem(BaseModel):
    id: str
    name: str
    description: str | None = None
    type: str
    score: float = 0.0


class SearchResponse(BaseModel):
    query: str
    workflows: list[SearchResultItem]
    agents: list[SearchResultItem]
    knowledge_bases: list[SearchResultItem]
    templates: list[SearchResultItem]
    total: int
