from pathlib import Path

from app.services.loaders.base import DocumentLoadError, LoadResult, LoadedFragment


class WordDocumentLoader:
    loader_name = "Docx2txtLoader"
    extensions = (".docx", ".doc")

    def load(self, file_path: Path) -> LoadResult:
        from langchain_community.document_loaders import Docx2txtLoader

        raw_docs = Docx2txtLoader(str(file_path)).load()
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
            raise DocumentLoadError("Word document did not yield any readable text.")

        return LoadResult(loader_name=self.loader_name, fragments=fragments)
