"""In-memory store of recent query results (per server process), addressed by query id."""

from collections import OrderedDict

from samovar_agent.domain.errors import UnknownResult
from samovar_agent.domain.result import StoredResult


class ResultStore:
    def __init__(self, capacity: int) -> None:
        self._capacity = capacity
        self._items: OrderedDict[str, StoredResult] = OrderedDict()

    def put(self, result: StoredResult) -> None:
        self._items[result.query_id] = result
        self._items.move_to_end(result.query_id)
        while len(self._items) > self._capacity:
            self._items.popitem(last=False)

    def get(self, query_id: str) -> StoredResult:
        try:
            return self._items[query_id]
        except KeyError as error:
            raise UnknownResult(f"Unknown or expired query_id {query_id!r}: run the query again.") from error
