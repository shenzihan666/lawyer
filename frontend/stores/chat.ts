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

export type ChatStep = {
  key: string;
  label: string;
  detail: string;
  status: string;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  isThinking: boolean;
  isStreaming: boolean;
  steps: ChatStep[];
  citations: AnswerCitation[];
  meta: Record<string, unknown>;
  trace: Record<string, unknown> | null;
  error: string | null;
};

type StreamResultEvent = {
  type: "result";
  answer: string;
  citations: AnswerCitation[];
  meta: Record<string, unknown>;
};

type StreamTraceEvent = {
  type: "trace";
  rag_trace?: Record<string, unknown>;
};

type StreamStepEvent = {
  type: "rag_step";
  step: ChatStep;
};

type StreamContentEvent = {
  type: "content";
  content: string;
};

type StreamErrorEvent = {
  type: "error";
  content: string;
};

type StreamEvent =
  | StreamResultEvent
  | StreamTraceEvent
  | StreamStepEvent
  | StreamContentEvent
  | StreamErrorEvent;

function createMessageId(role: "user" | "assistant") {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `${role}-${crypto.randomUUID()}`;
  }

  return `${role}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export const useChatStore = defineStore("chat", () => {
  const runtimeConfig = useRuntimeConfig();
  const apiBase = runtimeConfig.public.apiBase as string;
  const toast = useToast();

  const prompt = ref("");
  const topK = ref(5);
  const selectedDocumentIds = ref<string[]>([]);
  const messages = ref<ChatMessage[]>([]);
  const isResponding = ref(false);
  const abortController = shallowRef<AbortController | null>(null);

  const assistantMessages = computed(() =>
    messages.value.filter((message) => message.role === "assistant"),
  );

  const lastAssistantMessage = computed(
    () => assistantMessages.value[assistantMessages.value.length - 1] ?? null,
  );

  const hasAnswered = computed(() =>
    assistantMessages.value.some(
      (message) =>
        Boolean(message.text.trim()) ||
        message.citations.length > 0 ||
        Boolean(message.error),
    ),
  );

  function createAssistantMessage(): ChatMessage {
    return {
      id: createMessageId("assistant"),
      role: "assistant",
      text: "",
      isThinking: true,
      isStreaming: true,
      steps: [],
      citations: [],
      meta: {},
      trace: null,
      error: null,
    };
  }

  function getMessageById(messageId: string) {
    return messages.value.find((message) => message.id === messageId) ?? null;
  }

  function applyStreamEvent(messageId: string, event: StreamEvent | string) {
    const message = getMessageById(messageId);
    if (!message) return;

    if (typeof event === "string") {
      message.isThinking = false;
      message.isStreaming = false;
      return;
    }

    switch (event.type) {
      case "content":
        if (event.content) {
          message.isThinking = false;
          message.text += event.content;
        }
        break;
      case "rag_step":
        message.steps.push({
          key: String(event.step?.key || `step-${message.steps.length + 1}`),
          label: String(event.step?.label || "处理中"),
          detail: String(event.step?.detail || ""),
          status: String(event.step?.status || "running"),
        });
        break;
      case "trace":
        message.trace = event.rag_trace ?? null;
        break;
      case "result":
        message.text = event.answer || message.text;
        message.citations = event.citations || [];
        message.meta = event.meta || {};
        message.trace =
          (event.meta?.search_meta as Record<string, unknown> | undefined) ??
          message.trace;
        message.isThinking = false;
        message.isStreaming = false;
        break;
      case "error":
        message.error = event.content;
        message.isThinking = false;
        message.isStreaming = false;
        if (!message.text.trim()) {
          message.text = `生成失败：${event.content}`;
        }
        break;
    }
  }

  function parseSseBlock(block: string) {
    const lines = block
      .replace(/\r/g, "")
      .split("\n")
      .filter((line) => line.startsWith("data:"));

    if (!lines.length) return null;

    return lines.map((line) => line.slice(5).trimStart()).join("\n");
  }

  async function ask() {
    const query = prompt.value.trim();
    if (!query) {
      toast.add({
        title: "请输入问题",
        description: "输入法律问题后再开始问答。",
        color: "warning",
      });
      return;
    }

    if (isResponding.value) {
      return;
    }

    const userMessage: ChatMessage = {
      id: createMessageId("user"),
      role: "user",
      text: query,
      isThinking: false,
      isStreaming: false,
      steps: [],
      citations: [],
      meta: {},
      trace: null,
      error: null,
    };
    const assistantMessage = createAssistantMessage();

    messages.value.push(userMessage, assistantMessage);
    prompt.value = "";
    isResponding.value = true;

    const controller = new AbortController();
    abortController.value = controller;

    try {
      const response = await fetch(`${apiBase}/chat/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          query,
          top_k: topK.value,
          document_ids: selectedDocumentIds.value,
        }),
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      if (!response.body) {
        throw new Error("Streaming response body is unavailable");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          buffer += decoder.decode();
          break;
        }

        buffer += decoder.decode(value, { stream: true });

        let boundaryIndex = buffer.indexOf("\n\n");
        while (boundaryIndex !== -1) {
          const block = buffer.slice(0, boundaryIndex);
          buffer = buffer.slice(boundaryIndex + 2);

          const data = parseSseBlock(block);
          if (data) {
            if (data === "[DONE]") {
              applyStreamEvent(assistantMessage.id, data);
            } else {
              applyStreamEvent(
                assistantMessage.id,
                JSON.parse(data) as StreamEvent,
              );
            }
          }

          boundaryIndex = buffer.indexOf("\n\n");
        }
      }

      const trailingData = parseSseBlock(buffer);
      if (trailingData) {
        if (trailingData === "[DONE]") {
          applyStreamEvent(assistantMessage.id, trailingData);
        } else {
          applyStreamEvent(
            assistantMessage.id,
            JSON.parse(trailingData) as StreamEvent,
          );
        }
      }
    } catch (error) {
      const message = getMessageById(assistantMessage.id);
      if (message) {
        message.isThinking = false;
        message.isStreaming = false;
        message.error = String(error);
        if (!message.text.trim()) {
          message.text = `生成失败：${String(error)}`;
        }
      }

      if (!(error instanceof DOMException && error.name === "AbortError")) {
        toast.add({
          title: "问答失败",
          description: String(error),
          color: "error",
        });
      }
    } finally {
      isResponding.value = false;
      abortController.value = null;
    }
  }

  function stop() {
    abortController.value?.abort();
  }

  function reset() {
    abortController.value?.abort();
    messages.value = [];
    isResponding.value = false;
    abortController.value = null;
  }

  return {
    prompt,
    topK,
    selectedDocumentIds,
    messages,
    assistantMessages,
    lastAssistantMessage,
    isResponding,
    hasAnswered,
    ask,
    stop,
    reset,
  };
});
