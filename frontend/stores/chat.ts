import { defineStore } from "pinia";

export type AnswerCitation = {
  citation_number: number;
  chunk_id: string;
  document_id: string;
  root_chunk_id: string;
  parent_chunk_id: string | null;
  chunk_level: number;
  chunk_index: number;
  page_number: number;
  original_filename: string;
  snippet: string;
  score: number;
  metadata: Record<string, unknown>;
};

export type AnswerResponse = {
  answer: string;
  citations: AnswerCitation[];
  meta: Record<string, unknown>;
};

export const useChatStore = defineStore("chat", () => {
  const runtimeConfig = useRuntimeConfig();
  const apiBase = runtimeConfig.public.apiBase as string;
  const toast = useToast();

  const prompt = ref("");
  const topK = ref(5);
  const selectedDocumentIds = ref<string[]>([]);
  const answer = ref("");
  const citations = ref<AnswerCitation[]>([]);
  const meta = ref<Record<string, unknown>>({});
  const isResponding = ref(false);
  const hasAnswered = ref(false);

  async function ask() {
    if (!prompt.value.trim()) {
      toast.add({
        title: "请输入问题",
        description: "输入法律问题后再开始问答。",
        color: "warning",
      });
      return;
    }

    isResponding.value = true;
    try {
      const payload = await $fetch<AnswerResponse>(`${apiBase}/chat/answer`, {
        method: "POST",
        body: {
          query: prompt.value.trim(),
          top_k: topK.value,
          document_ids: selectedDocumentIds.value,
        },
      });
      answer.value = payload.answer;
      citations.value = payload.citations;
      meta.value = payload.meta;
      hasAnswered.value = true;
    } catch (error) {
      toast.add({
        title: "问答失败",
        description: String(error),
        color: "error",
      });
    } finally {
      isResponding.value = false;
    }
  }

  function reset() {
    answer.value = "";
    citations.value = [];
    meta.value = {};
    hasAnswered.value = false;
  }

  return {
    prompt,
    topK,
    selectedDocumentIds,
    answer,
    citations,
    meta,
    isResponding,
    hasAnswered,
    ask,
    reset,
  };
});
