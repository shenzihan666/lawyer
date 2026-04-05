import { defineStore } from "pinia";
import { useConversationsStore } from "./conversations";

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

type ConversationRuntimeState = {
  threadId: string | null;
  messages: ChatMessage[];
  isResponding: boolean;
  abortController: AbortController | null;
  hasLoadedHistory: boolean;
};

const DEFAULT_CONVERSATION_TITLE = "新对话";

function createMessageId(role: "user" | "assistant") {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `${role}-${crypto.randomUUID()}`;
  }

  return `${role}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function createDraftSessionKey() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `draft-${crypto.randomUUID()}`;
  }

  return `draft-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function createConversationState(threadId: string | null): ConversationRuntimeState {
  return {
    threadId,
    messages: [],
    isResponding: false,
    abortController: null,
    hasLoadedHistory: false,
  };
}

export const useChatStore = defineStore("chat", () => {
  const runtimeConfig = useRuntimeConfig();
  const apiBase = runtimeConfig.public.apiBase as string;
  const toast = useToast();
  const conversationsStore = useConversationsStore();

  const prompt = ref("");
  const topK = ref(5);
  const selectedDocumentIds = ref<string[]>([]);

  const sessionStates = ref<Record<string, ConversationRuntimeState>>({});
  const activeSessionKey = ref(createDraftSessionKey());
  sessionStates.value[activeSessionKey.value] = createConversationState(null);

  function ensureSessionState(sessionKey: string, threadId: string | null = null) {
    const existing = sessionStates.value[sessionKey];
    if (existing) {
      if (threadId !== null && existing.threadId !== threadId) {
        existing.threadId = threadId;
      }
      return existing;
    }

    const state = createConversationState(threadId);
    sessionStates.value[sessionKey] = state;
    return state;
  }

  function findSessionKeyByThreadId(targetThreadId: string) {
    for (const [sessionKey, state] of Object.entries(sessionStates.value)) {
      if (state.threadId === targetThreadId || sessionKey === targetThreadId) {
        return sessionKey;
      }
    }

    return null;
  }

  function getActiveState() {
    return ensureSessionState(activeSessionKey.value);
  }

  const messages = computed(() => getActiveState().messages);
  const isResponding = computed(() => getActiveState().isResponding);
  const threadId = computed(() => getActiveState().threadId);

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

  const respondingThreadIds = computed(() =>
    Object.values(sessionStates.value)
      .filter((state) => state.isResponding && state.threadId)
      .map((state) => state.threadId as string),
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

  function upsertConversationSnapshot(
    targetThreadId: string,
    query: string,
    state: ConversationRuntimeState,
  ) {
    const now = new Date().toISOString();
    const existing = conversationsStore.conversations.find(
      (item) => item.thread_id === targetThreadId,
    );

    conversationsStore.upsertConversation({
      thread_id: targetThreadId,
      title: existing?.title || DEFAULT_CONVERSATION_TITLE,
      created_at: existing?.created_at || now,
      updated_at: now,
      message_count: Math.max(existing?.message_count ?? 0, state.messages.length),
      last_message_preview: query.slice(0, 200),
    });
  }

  function getMessageById(
    state: ConversationRuntimeState,
    messageId: string,
  ) {
    return state.messages.find((message) => message.id === messageId) ?? null;
  }

  function applyStreamEvent(
    state: ConversationRuntimeState,
    messageId: string,
    event: StreamEvent | string,
  ) {
    const message = getMessageById(state, messageId);
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

  function renameSessionKey(oldKey: string, newThreadId: string) {
    if (oldKey === newThreadId) {
      const current = ensureSessionState(oldKey, newThreadId);
      current.threadId = newThreadId;
      return newThreadId;
    }

    const current = ensureSessionState(oldKey, newThreadId);
    const existingTarget = sessionStates.value[newThreadId];
    const nextState = existingTarget ?? current;
    nextState.threadId = newThreadId;

    if (existingTarget && existingTarget !== current) {
      if (!existingTarget.messages.length && current.messages.length) {
        existingTarget.messages = current.messages;
      }
      existingTarget.isResponding = current.isResponding;
      existingTarget.abortController = current.abortController;
      existingTarget.hasLoadedHistory =
        existingTarget.hasLoadedHistory || current.hasLoadedHistory;
    } else {
      sessionStates.value[newThreadId] = current;
    }

    delete sessionStates.value[oldKey];

    if (activeSessionKey.value === oldKey) {
      activeSessionKey.value = newThreadId;
    }

    return newThreadId;
  }

  async function loadMessagesForState(
    sessionKey: string,
    targetThreadId: string,
  ) {
    const state = ensureSessionState(sessionKey, targetThreadId);
    if (state.hasLoadedHistory || state.isResponding || state.messages.length > 0) {
      return;
    }

    try {
      const response = await fetch(
        `${apiBase}/conversations/${targetThreadId}/messages`,
      );
      if (!response.ok) {
        state.messages = [];
        return;
      }

      const data = await response.json();
      state.messages = (data.messages ?? [])
        .filter(
          (message: { role: string; content: string }) =>
            message.role === "user" || message.role === "assistant",
        )
        .map(
          (message: {
            role: "user" | "assistant";
            content: string;
            citations: AnswerCitation[];
            meta: Record<string, unknown>;
          }) => ({
            id: createMessageId(message.role),
            role: message.role,
            text: message.content,
            isThinking: false,
            isStreaming: false,
            steps: [],
            citations: message.citations ?? [],
            meta: message.meta ?? {},
            trace: null,
            error: null,
          }),
        );
      state.hasLoadedHistory = true;
    } catch {
      state.messages = [];
    }
  }

  function startNewConversation() {
    const current = getActiveState();
    if (!current.threadId && !current.isResponding && current.messages.length === 0) {
      conversationsStore.setActive(null);
      return activeSessionKey.value;
    }

    const sessionKey = createDraftSessionKey();
    ensureSessionState(sessionKey, null);
    activeSessionKey.value = sessionKey;
    conversationsStore.setActive(null);
    prompt.value = "";
    return sessionKey;
  }

  async function switchConversation(targetThreadId: string | null) {
    if (!targetThreadId) {
      startNewConversation();
      return;
    }

    const existingSessionKey =
      findSessionKeyByThreadId(targetThreadId) ?? targetThreadId;
    ensureSessionState(existingSessionKey, targetThreadId);
    activeSessionKey.value = existingSessionKey;
    conversationsStore.setActive(targetThreadId);
    await loadMessagesForState(existingSessionKey, targetThreadId);
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

    const sessionKeyAtStart = activeSessionKey.value;
    let state = ensureSessionState(sessionKeyAtStart);
    if (state.isResponding) {
      return;
    }

    const existingThreadId = state.threadId;
    const isNewConversation = !existingThreadId;
    let resolvedThreadId = existingThreadId;
    let resolvedSessionKey = sessionKeyAtStart;

    if (!resolvedThreadId) {
      try {
        resolvedThreadId = await conversationsStore.createConversation();
        resolvedSessionKey = renameSessionKey(sessionKeyAtStart, resolvedThreadId);
        state = ensureSessionState(resolvedSessionKey, resolvedThreadId);
        state.threadId = resolvedThreadId;

        if (activeSessionKey.value === resolvedSessionKey) {
          conversationsStore.setActive(resolvedThreadId);
        }

        upsertConversationSnapshot(resolvedThreadId, query, state);
      } catch {
        resolvedThreadId = null;
        resolvedSessionKey = sessionKeyAtStart;
        state = ensureSessionState(resolvedSessionKey);
      }
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

    state.messages.push(userMessage, assistantMessage);
    state.isResponding = true;
    prompt.value = "";

    const controller = new AbortController();
    state.abortController = controller;

    try {
      const response = await fetch(`${apiBase}/agent/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          query,
          thread_id: resolvedThreadId,
          top_k: topK.value,
          document_ids: selectedDocumentIds.value,
        }),
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const responseThreadId = response.headers.get("x-thread-id");
      if (responseThreadId) {
        resolvedThreadId = responseThreadId;
        resolvedSessionKey = renameSessionKey(sessionKeyAtStart, responseThreadId);
        const currentState = ensureSessionState(resolvedSessionKey, responseThreadId);
        currentState.threadId = responseThreadId;
        upsertConversationSnapshot(responseThreadId, query, currentState);

        if (activeSessionKey.value === resolvedSessionKey) {
          conversationsStore.setActive(responseThreadId);
        }
      } else if (resolvedThreadId) {
        upsertConversationSnapshot(resolvedThreadId, query, state);
        if (activeSessionKey.value === sessionKeyAtStart) {
          conversationsStore.setActive(resolvedThreadId);
        }
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
            const latestState = ensureSessionState(
              resolvedSessionKey,
              resolvedThreadId,
            );

            if (data === "[DONE]") {
              applyStreamEvent(latestState, assistantMessage.id, data);
            } else {
              applyStreamEvent(
                latestState,
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
        const latestState = ensureSessionState(
          resolvedSessionKey,
          resolvedThreadId,
        );

        if (trailingData === "[DONE]") {
          applyStreamEvent(latestState, assistantMessage.id, trailingData);
        } else {
          applyStreamEvent(
            latestState,
            assistantMessage.id,
            JSON.parse(trailingData) as StreamEvent,
          );
        }
      }
    } catch (error) {
      const latestState = ensureSessionState(resolvedSessionKey, resolvedThreadId);
      const message = getMessageById(latestState, assistantMessage.id);
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
      const latestState = ensureSessionState(resolvedSessionKey, resolvedThreadId);

      latestState.isResponding = false;
      latestState.abortController = null;
      latestState.hasLoadedHistory = latestState.hasLoadedHistory || Boolean(latestState.threadId);

      if (latestState.threadId) {
        upsertConversationSnapshot(latestState.threadId, query, latestState);
        void conversationsStore.refreshList();

        if (isNewConversation && import.meta.client) {
          window.setTimeout(() => {
            void conversationsStore.refreshList();
          }, 1200);
        }
      }
    }
  }

  function stop() {
    getActiveState().abortController?.abort();
  }

  function isConversationResponding(targetThreadId: string) {
    const sessionKey = findSessionKeyByThreadId(targetThreadId);
    return sessionKey ? ensureSessionState(sessionKey).isResponding : false;
  }

  function removeConversation(threadIdToRemove: string) {
    const sessionKey = findSessionKeyByThreadId(threadIdToRemove);
    if (!sessionKey) {
      return;
    }

    const state = ensureSessionState(sessionKey);
    state.abortController?.abort();

    if (activeSessionKey.value === sessionKey) {
      delete sessionStates.value[sessionKey];
      const draftKey = createDraftSessionKey();
      activeSessionKey.value = draftKey;
      sessionStates.value[draftKey] = createConversationState(null);
      conversationsStore.setActive(null);
      prompt.value = "";
      return;
    }

    delete sessionStates.value[sessionKey];
  }

  function reset() {
    for (const state of Object.values(sessionStates.value)) {
      state.abortController?.abort();
    }

    sessionStates.value = {};
    activeSessionKey.value = createDraftSessionKey();
    sessionStates.value[activeSessionKey.value] = createConversationState(null);
    prompt.value = "";
    selectedDocumentIds.value = [];
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
    threadId,
    respondingThreadIds,
    ask,
    stop,
    reset,
    startNewConversation,
    switchConversation,
    isConversationResponding,
    removeConversation,
  };
});
