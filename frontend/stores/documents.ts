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

export type VectorizationProgress = {
  active: boolean;
  document_ids: string[];
  total: number;
  completed: number;
  indexed: number;
  failed: number;
  indexing: number;
  queued: number;
  percent: number;
  label: string;
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

  const vectorizationProgress = reactive<VectorizationProgress>({
    active: false,
    document_ids: [],
    total: 0,
    completed: 0,
    indexed: 0,
    failed: 0,
    indexing: 0,
    queued: 0,
    percent: 0,
    label: "",
  });

  const toast = useToast();
  let vectorizationPollTimer: ReturnType<typeof setInterval> | null = null;
  let vectorizationResetTimer: ReturnType<typeof setTimeout> | null = null;

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

  function clearVectorizationPollTimer() {
    if (!vectorizationPollTimer) return;
    clearInterval(vectorizationPollTimer);
    vectorizationPollTimer = null;
  }

  function clearVectorizationResetTimer() {
    if (!vectorizationResetTimer) return;
    clearTimeout(vectorizationResetTimer);
    vectorizationResetTimer = null;
  }

  function resetVectorizationProgress() {
    clearVectorizationPollTimer();
    clearVectorizationResetTimer();

    vectorizationProgress.active = false;
    vectorizationProgress.document_ids = [];
    vectorizationProgress.total = 0;
    vectorizationProgress.completed = 0;
    vectorizationProgress.indexed = 0;
    vectorizationProgress.failed = 0;
    vectorizationProgress.indexing = 0;
    vectorizationProgress.queued = 0;
    vectorizationProgress.percent = 0;
    vectorizationProgress.label = "";
  }

  function updateVectorizationProgress() {
    if (!vectorizationProgress.document_ids.length) return;

    let indexed = 0;
    let failed = 0;
    let indexing = 0;
    let queued = 0;

    for (const id of vectorizationProgress.document_ids) {
      const document = documents.value.find((item) => item.id === id);
      if (!document) continue;

      switch (document.vector_status) {
        case "indexed":
          indexed += 1;
          break;
        case "failed":
          failed += 1;
          break;
        case "indexing":
          indexing += 1;
          break;
        case "queued":
          queued += 1;
          break;
      }
    }

    const completed = indexed + failed;
    const total = Math.max(vectorizationProgress.total, 1);
    const weightedCompleted = completed + indexing * 0.65 + queued * 0.2;

    vectorizationProgress.completed = completed;
    vectorizationProgress.indexed = indexed;
    vectorizationProgress.failed = failed;
    vectorizationProgress.indexing = indexing;
    vectorizationProgress.queued = queued;
    vectorizationProgress.percent =
      completed >= vectorizationProgress.total
        ? 100
        : Math.min(
            99,
            Math.max(8, Math.round((weightedCompleted / total) * 100)),
          );

    if (completed >= vectorizationProgress.total) {
      vectorizationProgress.label =
        failed > 0 ? "Indexing finished with failures" : "Indexing finished";
      return;
    }

    if (indexing > 0) {
      vectorizationProgress.label = "Embedding and indexing document chunks";
      return;
    }

    if (queued > 0) {
      vectorizationProgress.label = "Queued and preparing document chunks";
      return;
    }

    vectorizationProgress.label = "Starting vectorization";
  }

  function scheduleVectorizationProgressReset() {
    clearVectorizationResetTimer();
    vectorizationResetTimer = setTimeout(() => {
      resetVectorizationProgress();
    }, 1600);
  }

  function startVectorizationTracking(ids: string[]) {
    clearVectorizationPollTimer();
    clearVectorizationResetTimer();

    const uniqueIds = [...new Set(ids)];
    vectorizationProgress.active = true;
    vectorizationProgress.document_ids = uniqueIds;
    vectorizationProgress.total = uniqueIds.length;
    vectorizationProgress.completed = 0;
    vectorizationProgress.indexed = 0;
    vectorizationProgress.failed = 0;
    vectorizationProgress.indexing = 0;
    vectorizationProgress.queued = 0;
    vectorizationProgress.percent = 8;
    vectorizationProgress.label = "Starting vectorization";
    updateVectorizationProgress();

    vectorizationPollTimer = setInterval(() => {
      void fetchDocuments({ showLoading: false, toastOnError: false }).catch(
        () => undefined,
      );
    }, 1200);
  }

  function finishVectorizationTracking() {
    vectorizationProgress.active = false;
    clearVectorizationPollTimer();
    scheduleVectorizationProgressReset();
  }

  async function fetchDocuments(options?: {
    showLoading?: boolean;
    toastOnError?: boolean;
  }) {
    const showLoading = options?.showLoading ?? true;
    const toastOnError = options?.toastOnError ?? true;

    if (showLoading) {
      isLoading.value = true;
    }

    try {
      const payload = await request<DocumentResponse>("/documents");
      applyResponse(payload);
      updateVectorizationProgress();
      return payload;
    } catch (error) {
      if (toastOnError) {
        toast.add({
          title: "Load failed",
          description: String(error),
          color: "error",
        });
      }
      throw error;
    } finally {
      if (showLoading) {
        isLoading.value = false;
      }
    }
  }

  async function refreshDocuments() {
    try {
      await fetchDocuments();
    } catch {
      return;
    }
  }

  async function uploadDocuments() {
    if (!stagedFiles.value.length) {
      toast.add({
        title: "Select documents",
        description: "Choose at least one file before uploading.",
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
        title: "Upload complete",
        description: `Imported ${payload.affected_ids?.length ?? 0} document(s).`,
        color: "success",
      });
    } catch (error) {
      toast.add({
        title: "Upload failed",
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
    startVectorizationTracking(ids);

    try {
      const payload = await request<DocumentResponse>("/documents/vectorize", {
        method: "POST",
        body: { document_ids: ids },
      });
      applyResponse(payload);
      updateVectorizationProgress();
      finishVectorizationTracking();
      selectedIds.value = selectedIds.value.filter((id) => !ids.includes(id));
      toast.add({
        title: "Indexing complete",
        description: `Processed ${payload.affected_ids?.length ?? 0} document(s).`,
        color: "success",
      });
    } catch (error) {
      void fetchDocuments({ showLoading: false, toastOnError: false }).catch(
        () => undefined,
      );
      vectorizationProgress.label = "Indexing request failed";
      finishVectorizationTracking();
      toast.add({
        title: "Indexing failed",
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
        title: "Deleted",
        description: `Removed ${payload.affected_ids?.length ?? 0} document(s).`,
        color: "success",
      });
    } catch (error) {
      toast.add({
        title: "Delete failed",
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
    vectorizationProgress,
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
