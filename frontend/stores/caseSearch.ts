import { defineStore } from "pinia";

export type PreviewFragmentItem = {
  fragment_index: number;
  page_number: number;
  content: string;
  metadata: Record<string, unknown>;
};

export type DocumentPreview = {
  asset_type: string;
  asset_id: string;
  title: string;
  original_filename: string;
  file_extension: string;
  mime_type: string | null;
  preview_excerpt: string | null;
  file_url: string;
  preview_url: string | null;
  preview_status: string;
  fragments: PreviewFragmentItem[];
  meta: Record<string, unknown>;
};

export type CaseSearchMatchedChunk = {
  chunk_id: string;
  page_number: number;
  score: number;
  content: string;
  metadata: Record<string, unknown>;
};

export type CaseSearchQueryAssetSummary = {
  id: string;
  original_filename: string;
  file_extension: string;
  mime_type: string | null;
  file_size: number;
  extraction_status: string;
  preview_status: string;
  preview_excerpt: string | null;
  created_at: string;
};

export type CaseSearchListItem = {
  id: string;
  query_type: string;
  query_text: string | null;
  prepared_query: string;
  top_k: number;
  scope_document_ids: string[];
  status: string;
  result_count: number;
  query_asset: CaseSearchQueryAssetSummary | null;
  created_at: string;
  updated_at: string;
};

export type CaseSearchHitItem = {
  id: number;
  document_id: string;
  original_filename: string;
  preview_excerpt: string | null;
  rank: number;
  score: number;
  matched_chunk_count: number;
  matched_pages: number[];
  matched_chunk_ids: string[];
  matched_snippets: string[];
  top_chunks: CaseSearchMatchedChunk[];
  meta: Record<string, unknown>;
};

export type CaseSearchDetail = {
  item: CaseSearchListItem;
  hits: CaseSearchHitItem[];
};

export const useCaseSearchStore = defineStore("case-search", () => {
  const runtimeConfig = useRuntimeConfig();
  const apiBase = runtimeConfig.public.apiBase as string;
  const toast = useToast();

  const mode = ref<"text" | "upload">("text");
  const queryText = ref("");
  const pendingFile = ref<File | null>(null);
  const topK = ref(5);
  const selectedDocumentIds = ref<string[]>([]);

  const searches = ref<CaseSearchListItem[]>([]);
  const detail = ref<CaseSearchDetail | null>(null);
  const preview = ref<DocumentPreview | null>(null);
  const activeSearchId = ref<string | null>(null);
  const activeHitId = ref<number | null>(null);
  const previewTab = ref<"structured" | "original">("structured");

  const isCreating = ref(false);
  const isLoadingHistory = ref(false);
  const isLoadingDetail = ref(false);
  const isLoadingPreview = ref(false);

  const activeHit = computed(() =>
    detail.value?.hits.find((item) => item.id === activeHitId.value) ?? null,
  );

  async function request<T>(path: string, options?: Parameters<typeof $fetch<T>>[1]) {
    return await $fetch<T>(`${apiBase}${path}`, options);
  }

  async function fetchHistory() {
    isLoadingHistory.value = true;
    try {
      const payload = await request<{ items: CaseSearchListItem[] }>("/case-searches");
      searches.value = payload.items;
      return payload.items;
    } catch (error) {
      toast.add({ title: "历史加载失败", description: String(error), color: "error" });
      return [];
    } finally {
      isLoadingHistory.value = false;
    }
  }

  async function fetchDetail(searchId: string, options?: { quiet?: boolean }) {
    if (!options?.quiet) {
      isLoadingDetail.value = true;
    }
    try {
      const payload = await request<CaseSearchDetail>(`/case-searches/${searchId}`);
      detail.value = payload;
      activeSearchId.value = payload.item.id;
      const existing = searches.value.findIndex((item) => item.id === payload.item.id);
      if (existing === -1) {
        searches.value = [payload.item, ...searches.value];
      } else {
        const next = [...searches.value];
        next[existing] = payload.item;
        searches.value = next;
      }
      const firstHit = payload.hits[0];
      if (firstHit) {
        await selectHit(firstHit.id, { quiet: true });
      } else {
        activeHitId.value = null;
        preview.value = null;
      }
      return payload;
    } catch (error) {
      if (!options?.quiet) {
        toast.add({ title: "结果加载失败", description: String(error), color: "error" });
      }
      throw error;
    } finally {
      if (!options?.quiet) {
        isLoadingDetail.value = false;
      }
    }
  }

  async function createSearch() {
    if (mode.value === "text" && !queryText.value.trim()) {
      toast.add({ title: "请输入案件描述", description: "至少输入一段案情或争议焦点。", color: "warning" });
      return;
    }
    if (mode.value === "upload" && !pendingFile.value) {
      toast.add({ title: "请上传待比对案件", description: "上传文件后再发起类案检索。", color: "warning" });
      return;
    }

    const formData = new FormData();
    formData.append("top_k", String(topK.value));
    for (const documentId of selectedDocumentIds.value) {
      formData.append("document_ids", documentId);
    }
    if (mode.value === "text") {
      formData.append("query_text", queryText.value.trim());
    } else if (pendingFile.value) {
      formData.append("file", pendingFile.value);
    }

    isCreating.value = true;
    try {
      const payload = await request<CaseSearchDetail>("/case-searches", {
        method: "POST",
        body: formData,
      });
      detail.value = payload;
      activeSearchId.value = payload.item.id;
      searches.value = [payload.item, ...searches.value.filter((item) => item.id !== payload.item.id)];
      const firstHit = payload.hits[0];
      if (firstHit) {
        await selectHit(firstHit.id, { quiet: true, preloaded: payload });
      } else {
        preview.value = null;
        activeHitId.value = null;
      }
      if (mode.value === "upload") {
        pendingFile.value = null;
      }
      toast.add({
        title: "类案检索已完成",
        description: payload.hits.length
          ? `已返回 ${payload.hits.length} 条案件结果。`
          : "当前没有命中结果。",
        color: "success",
      });
    } catch (error) {
      toast.add({ title: "类案检索失败", description: String(error), color: "error" });
    } finally {
      isCreating.value = false;
    }
  }

  async function selectSearch(searchId: string) {
    await fetchDetail(searchId);
  }

  async function selectHit(
    hitId: number,
    options?: { quiet?: boolean; preloaded?: CaseSearchDetail },
  ) {
    const sourceDetail = options?.preloaded ?? detail.value;
    const hit = sourceDetail?.hits.find((item) => item.id === hitId) ?? null;
    activeHitId.value = hitId;
    preview.value = null;
    if (!hit) {
      return;
    }

    if (!options?.quiet) {
      isLoadingPreview.value = true;
    }
    try {
      const payload = await request<DocumentPreview>(`/documents/${hit.document_id}/preview`);
      preview.value = payload;
    } catch (error) {
      toast.add({ title: "预览加载失败", description: String(error), color: "error" });
    } finally {
      if (!options?.quiet) {
        isLoadingPreview.value = false;
      }
    }
  }

  async function deleteSearch(searchId: string) {
    try {
      await request(`/case-searches/${searchId}`, { method: "DELETE" });
      searches.value = searches.value.filter((item) => item.id !== searchId);
      if (activeSearchId.value === searchId) {
        detail.value = null;
        preview.value = null;
        activeSearchId.value = null;
        activeHitId.value = null;
      }
      toast.add({ title: "历史已删除", description: "该次类案检索记录已移除。", color: "success" });
    } catch (error) {
      toast.add({ title: "删除失败", description: String(error), color: "error" });
    }
  }

  function setPendingFile(file: File | null) {
    pendingFile.value = file;
  }

  function resetComposer() {
    queryText.value = "";
    pendingFile.value = null;
  }

  return {
    mode,
    queryText,
    pendingFile,
    topK,
    selectedDocumentIds,
    searches,
    detail,
    preview,
    activeSearchId,
    activeHitId,
    previewTab,
    activeHit,
    isCreating,
    isLoadingHistory,
    isLoadingDetail,
    isLoadingPreview,
    fetchHistory,
    fetchDetail,
    createSearch,
    selectSearch,
    selectHit,
    deleteSearch,
    setPendingFile,
    resetComposer,
  };
});
