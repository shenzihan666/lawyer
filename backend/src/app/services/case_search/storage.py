from app.services.documents.storage import StoredFile, UploadStorage


class CaseSearchStorage(UploadStorage):
    QUERY_NAMESPACE = "case-search-queries"
    PREVIEW_NAMESPACE = "case-search-assets"

    def save_query_upload(self, upload) -> StoredFile:
        return self.save_upload(upload, namespace=self.QUERY_NAMESPACE)
