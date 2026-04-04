from pathlib import Path

from app.services.loaders.base import DocumentLoadError, LoadResult, LoadedFragment


class PdfDocumentLoader:
    loader_name = "PyPDFLoader"
    extensions = (".pdf",)

    def load(self, file_path: Path) -> LoadResult:
        from langchain_community.document_loaders import PyPDFLoader

        raw_docs = PyPDFLoader(str(file_path)).load()
        fragments: list[LoadedFragment] = []

        for index, raw_doc in enumerate(raw_docs):
            content = raw_doc.page_content.strip()
            if not content:
                continue

            metadata = dict(raw_doc.metadata or {})
            page_number = int(metadata.get("page", index)) + 1
            fragments.append(
                LoadedFragment(
                    fragment_index=len(fragments),
                    page_number=page_number,
                    content=content,
                    metadata=metadata,
                )
            )

        if not fragments:
            raise DocumentLoadError("PDF did not yield any readable text.")

        return LoadResult(loader_name=self.loader_name, fragments=fragments)
