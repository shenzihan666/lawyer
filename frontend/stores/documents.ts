import { defineStore } from "pinia";

export type DocumentItem = {
  id: string;
  original_filename: string;
  stored_filename: string;
  storage_path: string;
  file_extension: string;
  mime_type: string | null;
  loader_name: string;
  sha256: string;
  file_size: number;
  page_count: number;
  raw_doc_count: number;
  preview_excerpt: string | null;
  ingestion_status: string;
  vector_status: string;
  failure_reason: string | null;
  trace_metadata: Record<string, unknown>;
  uploaded_at: string;
  updated_at: string;
  deleted_at: string | null;
};

export type DocumentSummary = {
  total: number;
  ready: number;
  failed: number;
  vector_queued: number;
  vector_indexed: number;
  vector_failed: number;
  deleted: number;
};

export type DocumentResponse = {
  items: DocumentItem[];
  summary: DocumentSummary;
  affected_ids?: string[];
};

export const useDocumentStore = defineStore("documents", () => {
  const runtimeConfig = useRuntimeConfig();
  const apiBase = runtimeConfig.public.apiBase as string;

  const documents = ref<DocumentItem[]>([]);
  const stagedFiles = ref<File[]>([]);
  const selectedIds = ref<string[]>([]);

  const isLoading = ref(false);
  const isWorking = ref(false);

  const summary = reactive<DocumentSummary>({
    total: 0,
    ready: 0,
    failed: 0,
    vector_queued: 0,
    vector_indexed: 0,
    vector_failed: 0,
    deleted: 0,
  });

  const toast = useToast();

  const hasSelection = computed(() => selectedIds.value.length > 0);

  function applyResponse(payload: DocumentResponse) {
    documents.value = payload.items;
    summary.total = payload.summary.total;
    summary.ready = payload.summary.ready;
    summary.failed = payload.summary.failed;
    summary.vector_queued = payload.summary.vector_queued;
    summary.vector_indexed = payload.summary.vector_indexed;
    summary.vector_failed = payload.summary.vector_failed;
    summary.deleted = payload.summary.deleted;
  }

  function mergeFiles(files: File[]) {
    const fileMap = new Map<string, File>();
    for (const file of [...stagedFiles.value, ...files]) {
      fileMap.set(`${file.name}-${file.size}-${file.lastModified}`, file);
    }
    stagedFiles.value = [...fileMap.values()];
  }

  function removeStagedFile(target: File) {
    stagedFiles.value = stagedFiles.value.filter(
      (file) =>
        file.name !== target.name ||
        file.size !== target.size ||
        file.lastModified !== target.lastModified,
    );
  }

  function clearStagedFiles() {
    stagedFiles.value = [];
  }

  async function request<T>(
    path: string,
    options?: Parameters<typeof $fetch<T>>[1],
  ) {
    return await $fetch<T>(`${apiBase}${path}`, options);
  }

  async function refreshDocuments() {
    isLoading.value = true;
    try {
      const payload = await request<DocumentResponse>("/documents");
      applyResponse(payload);
    } catch (error) {
      toast.add({
        title: "加载失败",
        description: String(error),
        color: "error",
      });
    } finally {
      isLoading.value = false;
    }
  }

  async function uploadDocuments() {
    if (!stagedFiles.value.length) {
      toast.add({
        title: "提示",
        description: "请先选择至少一个文档",
        color: "warning",
      });
      return;
    }

    const formData = new FormData();
    for (const file of stagedFiles.value) {
      formData.append("files", file);
    }

    isWorking.value = true;
    try {
      const payload = await request<DocumentResponse>("/documents/upload", {
        method: "POST",
        body: formData,
      });
      applyResponse(payload);
      stagedFiles.value = [];
      selectedIds.value = [];
      toast.add({
        title: "上传成功",
        description: `已导入 ${payload.affected_ids?.length ?? 0} 个文档`,
        color: "success",
      });
    } catch (error) {
      toast.add({
        title: "导入失败",
        description: String(error),
        color: "error",
      });
    } finally {
      isWorking.value = false;
    }
  }

  async function queueVectorization(ids: string[]) {
    if (!ids.length) return;
    isWorking.value = true;
    try {
      const payload = await request<DocumentResponse>("/documents/vectorize", {
        method: "POST",
        body: { document_ids: ids },
      });
      applyResponse(payload);
      selectedIds.value = selectedIds.value.filter((id) => !ids.includes(id));
      toast.add({
        title: "操作成功",
        description: `已完成 ${payload.affected_ids?.length ?? 0} 个文档的向量索引`,
        color: "success",
      });
    } catch (error) {
      toast.add({
        title: "操作失败",
        description: String(error),
        color: "error",
      });
    } finally {
      isWorking.value = false;
    }
  }

  async function deleteDocuments(ids: string[]) {
    if (!ids.length) return;
    isWorking.value = true;
    try {
      const payload = await request<DocumentResponse>("/documents/delete", {
        method: "POST",
        body: { document_ids: ids },
      });
      applyResponse(payload);
      selectedIds.value = selectedIds.value.filter((id) => !ids.includes(id));
      toast.add({
        title: "已删除",
        description: `成功删除 ${payload.affected_ids?.length ?? 0} 个文档`,
        color: "success",
      });
    } catch (error) {
      toast.add({
        title: "删除失败",
        description: String(error),
        color: "error",
      });
    } finally {
      isWorking.value = false;
    }
  }

  return {
    documents,
    stagedFiles,
    selectedIds,
    isLoading,
    isWorking,
    summary,
    hasSelection,
    refreshDocuments,
    uploadDocuments,
    queueVectorization,
    deleteDocuments,
    mergeFiles,
    removeStagedFile,
    clearStagedFiles,
  };
});
