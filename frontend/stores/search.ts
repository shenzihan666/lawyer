import { defineStore } from "pinia";

export type SearchResultItem = {
  chunk_id: string;
  document_id: string;
  root_chunk_id: string;
  parent_chunk_id: string | null;
  chunk_level: number;
  chunk_index: number;
  page_number: number;
  content: string;
  original_filename: string;
  score: number;
  metadata: Record<string, unknown>;
};

export type SearchResponse = {
  items: SearchResultItem[];
  meta: Record<string, unknown>;
};

export const useSearchStore = defineStore("search", () => {
  const runtimeConfig = useRuntimeConfig();
  const apiBase = runtimeConfig.public.apiBase as string;
  const toast = useToast();

  const query = ref("");
  const topK = ref(5);
  const selectedDocumentIds = ref<string[]>([]);
  const results = ref<SearchResultItem[]>([]);
  const meta = ref<Record<string, unknown>>({});
  const isSearching = ref(false);
  const hasSearched = ref(false);

  async function search() {
    if (!query.value.trim()) {
      toast.add({
        title: "请输入检索内容",
        description: "输入问题或关键词后再开始检索",
        color: "warning",
      });
      return;
    }

    isSearching.value = true;
    try {
      const payload = await $fetch<SearchResponse>(`${apiBase}/search`, {
        method: "POST",
        body: {
          query: query.value.trim(),
          top_k: topK.value,
          document_ids: selectedDocumentIds.value,
        },
      });
      results.value = payload.items;
      meta.value = payload.meta;
      hasSearched.value = true;
    } catch (error) {
      toast.add({
        title: "检索失败",
        description: String(error),
        color: "error",
      });
    } finally {
      isSearching.value = false;
    }
  }

  function reset() {
    results.value = [];
    meta.value = {};
    hasSearched.value = false;
  }

  return {
    query,
    topK,
    selectedDocumentIds,
    results,
    meta,
    isSearching,
    hasSearched,
    search,
    reset,
  };
});
