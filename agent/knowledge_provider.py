from __future__ import annotations
from abc import ABC, abstractmethod
from agent.knowledge_models import KnowledgeDoc


class KnowledgeProvider(ABC):

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def query(
        self,
        query: str,
        product_line_id: str,
        finance_flag: bool,
        limit: int = 10,
    ) -> list[KnowledgeDoc]: ...

    @abstractmethod
    def write(self, doc: KnowledgeDoc, actor_user_id: str) -> str:
        """写入知识条目，返回最终 slug。"""

    def shutdown(self) -> None:
        pass
