import { defineStore } from "pinia";

export type Conversation = {
  thread_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  last_message_preview: string | null;
};

export const useConversationsStore = defineStore("conversations", () => {
  const runtimeConfig = useRuntimeConfig();
  const apiBase = runtimeConfig.public.apiBase as string;

  const conversations = ref<Conversation[]>([]);
  const activeThreadId = ref<string | null>(null);
  const isLoading = ref(false);

  function sortConversations(items: Conversation[]) {
    return [...items].sort(
      (left, right) =>
        new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime(),
    );
  }

  function upsertConversation(conversation: Conversation) {
    const index = conversations.value.findIndex(
      (item) => item.thread_id === conversation.thread_id,
    );

    if (index === -1) {
      conversations.value = sortConversations([conversation, ...conversations.value]);
      return;
    }

    const next = [...conversations.value];
    next[index] = {
      ...next[index],
      ...conversation,
    };
    conversations.value = sortConversations(next);
  }

  async function fetchConversations() {
    isLoading.value = true;
    try {
      const response = await fetch(`${apiBase}/conversations`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      conversations.value = sortConversations(data.items ?? []);
    } catch {
      conversations.value = [];
    } finally {
      isLoading.value = false;
    }
  }

  async function createConversation(): Promise<string> {
    const response = await fetch(`${apiBase}/conversations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    const threadId: string = data.thread_id;
    upsertConversation(data);
    return threadId;
  }

  async function deleteConversation(threadId: string) {
    await fetch(`${apiBase}/conversations/${threadId}`, { method: "DELETE" });
    conversations.value = conversations.value.filter(
      (c) => c.thread_id !== threadId,
    );
    if (activeThreadId.value === threadId) {
      activeThreadId.value = null;
    }
  }

  async function renameConversation(threadId: string, title: string) {
    const response = await fetch(`${apiBase}/conversations/${threadId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = (await response.json()) as Conversation;
    upsertConversation(data);
  }

  function setActive(threadId: string | null) {
    activeThreadId.value = threadId;
  }

  function refreshList() {
    return fetchConversations();
  }

  return {
    conversations,
    activeThreadId,
    isLoading,
    fetchConversations,
    createConversation,
    deleteConversation,
    renameConversation,
    setActive,
    refreshList,
    upsertConversation,
  };
});
