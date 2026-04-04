from pathlib import Path

from app.services.loaders.base import DocumentLoadError, LoadResult, LoadedFragment


class ExcelDocumentLoader:
    loader_name = "UnstructuredExcelLoader"
    extensions = (".xlsx", ".xls")

    def load(self, file_path: Path) -> LoadResult:
        from langchain_community.document_loaders import UnstructuredExcelLoader

        raw_docs = UnstructuredExcelLoader(str(file_path), mode="elements").load()
        fragments: list[LoadedFragment] = []

        for raw_doc in raw_docs:
            content = raw_doc.page_content.strip()
            if not content:
                continue

            fragments.append(
                LoadedFragment(
                    fragment_index=len(fragments),
                    page_number=0,
                    content=content,
                    metadata=dict(raw_doc.metadata or {}),
                )
            )

        if not fragments:
            raise DocumentLoadError(
                "Excel document did not yield any readable cell text."
            )

        return LoadResult(loader_name=self.loader_name, fragments=fragments)
