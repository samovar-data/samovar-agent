"""The data catalog, loaded once per process and shared by the tools."""

from samovar_agent.domain.catalog import Catalog
from samovar_agent.ports.document import DocumentSource


class CatalogCache:
    def __init__(self, source: DocumentSource[Catalog]) -> None:
        self._source = source
        self._catalog: Catalog | None = None

    @property
    def loaded(self) -> Catalog | None:
        return self._catalog

    def __call__(self) -> Catalog:
        if self._catalog is None:
            self._catalog = self._source.load()
        return self._catalog
