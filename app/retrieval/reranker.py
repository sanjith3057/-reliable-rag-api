"""Optional cross-encoder reranker. Reads the query and a chunk together, so it is slower but sharper."""

from abc import ABC, abstractmethod


class Reranker(ABC):
    @abstractmethod
    def score(self, query: str, texts: list[str]) -> list[float]: ...


class CrossEncoderReranker(Reranker):
    def __init__(self, model_name: str):
        self.name = model_name
        self._model = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder  # heavy import, deferred

            self._model = CrossEncoder(self.name)
        return self._model

    def warm_up(self) -> None:
        self._load()

    def score(self, query: str, texts: list[str]) -> list[float]:
        return [float(value) for value in self._load().predict([[query, text] for text in texts])]
