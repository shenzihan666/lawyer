from pathlib import Path
import zipfile

from app.services.loaders.base import (
    DocumentLoadError,
    LoadResult,
    LoadedFragment,
    UnsupportedDocumentTypeError,
)


class WordDocumentLoader:
    loader_name = "Docx2txtLoader"
    extensions = (".docx",)

    def load(self, file_path: Path) -> LoadResult:
        if file_path.suffix.lower() == ".doc":
            raise UnsupportedDocumentTypeError(
                "Legacy '.doc' files are not supported. Please convert the file to '.docx' and try again."
            )

        from langchain_community.document_loaders import Docx2txtLoader

        try:
            raw_docs = Docx2txtLoader(str(file_path)).load()
        except zipfile.BadZipFile as exc:
            raise DocumentLoadError(
                "Word document could not be read as a valid '.docx' file. Please re-save or convert the file to '.docx' and try again."
            ) from exc

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
