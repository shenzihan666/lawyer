<script setup lang="ts">
import { storeToRefs } from "pinia";
import { useUiStore } from "../../stores/ui";
import { useConversationsStore } from "../../stores/conversations";
import { useChatStore } from "../../stores/chat";

const uiStore = useUiStore();
const chatStore = useChatStore();
const conversationsStore = useConversationsStore();
const { isMobileOpen, isSidebarCollapsed } = storeToRefs(uiStore);
const { conversations, activeThreadId } = storeToRefs(conversationsStore);
const route = useRoute();
const editingThreadId = ref<string | null>(null);
const renameDraft = ref("");

const navItems = [
  { label: "知识库", path: "/documents", icon: "i-lucide-book-open" },
  { label: "类案检索", path: "/search", icon: "i-lucide-search" },
  { label: "合同审查", path: "/contract-review", icon: "i-lucide-file-signature" },
  { label: "对方观点预判", path: "/opponent-analysis", icon: "i-lucide-shield-question" },
];

const shellClass = computed(() => [
  "fixed inset-y-0 left-0 z-40 transition-transform duration-300",
  isMobileOpen.value ? "translate-x-0" : "-translate-x-full",
  isSidebarCollapsed.value ? "md:-translate-x-full" : "md:translate-x-0",
]);

function isActive(path: string) {
  return route.path === path;
}

function isActiveConversation(threadId: string) {
  return route.path === "/chat" && activeThreadId.value === threadId;
}

function isEditingConversation(threadId: string) {
  return editingThreadId.value === threadId;
}

async function handleNewConversation() {
  chatStore.startNewConversation();
  if (route.path !== "/chat") {
    await navigateTo("/chat");
  }
  uiStore.closeMobile();
}

async function handleSelectConversation(threadId: string) {
  await chatStore.switchConversation(threadId);
  if (route.path !== "/chat") {
    await navigateTo("/chat");
  }
  uiStore.closeMobile();
}

async function handleDeleteConversation(threadId: string) {
  chatStore.removeConversation(threadId);
  await conversationsStore.deleteConversation(threadId);
  if (activeThreadId.value === null) {
    chatStore.startNewConversation();
    if (route.path !== "/chat") {
      await navigateTo("/chat");
    }
  }
}

async function handleRenameConversation(threadId: string) {
  const item = conversations.value.find((c) => c.thread_id === threadId);
  if (!item) return;
  editingThreadId.value = threadId;
  renameDraft.value = item.title;
  await nextTick();
  const input = document.getElementById(
    `conversation-rename-${threadId}`,
  ) as HTMLInputElement | null;
  input?.focus();
  input?.select();
}

function cancelRenameConversation() {
  editingThreadId.value = null;
  renameDraft.value = "";
}

async function submitRenameConversation(threadId: string) {
  const item = conversations.value.find((c) => c.thread_id === threadId);
  if (!item || editingThreadId.value !== threadId) return;

  const title = renameDraft.value.trim();
  if (!title) {
    cancelRenameConversation();
    return;
  }

  if (title !== item.title) {
    await conversationsStore.renameConversation(threadId, title);
  }
  cancelRenameConversation();
}

async function handleRenameBlur(threadId: string) {
  if (editingThreadId.value === threadId) {
    await submitRenameConversation(threadId);
  }
}

async function handleRenameKeydown(event: KeyboardEvent, threadId: string) {
  if (event.key === "Enter") {
    event.preventDefault();
    await submitRenameConversation(threadId);
    return;
  }

  if (event.key === "Escape") {
    event.preventDefault();
    cancelRenameConversation();
  }
}

function handleNavigate() {
  uiStore.closeMobile();
}

function isConversationBusy(threadId: string) {
  return chatStore.isConversationResponding(threadId);
}

function formatTime(dateStr: string) {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return "刚刚";
  if (diffMins < 60) return `${diffMins}分钟前`;
  if (diffHours < 24) return `${diffHours}小时前`;
  if (diffDays < 7) return `${diffDays}天前`;
  return date.toLocaleDateString("zh-CN", { month: "short", day: "numeric" });
}

onMounted(() => {
  conversationsStore.fetchConversations();
});

watch(
  () => route.path,
  () => {
    if (route.path === "/chat") {
      conversationsStore.refreshList();
    }
  },
);
</script>

<template>
  <div
    v-if="isMobileOpen"
    class="fixed inset-0 z-30 bg-zinc-950/20 backdrop-blur-sm md:hidden"
    @click="uiStore.closeMobile()"
  />

  <div :class="shellClass">
    <aside
      class="flex h-full w-[264px] flex-col border-r border-[#ebe5da] bg-[#f7f4ee] shadow-xl shadow-zinc-950/5 md:shadow-none"
    >
      <!-- Mobile close button -->
      <div class="flex items-center justify-end px-4 pb-4 pt-6 md:hidden">
        <UButton
          icon="i-lucide-x"
          color="neutral"
          variant="ghost"
          @click="uiStore.closeMobile()"
        />
      </div>

      <!-- New conversation button -->
      <div class="px-3 pt-3">
        <button
          class="flex w-full items-center gap-2.5 rounded-2xl px-3 py-3 text-left text-[15px] font-medium transition-colors bg-[#eef2ff] text-[#3158ff] ring-1 ring-[#d9e1ff] hover:bg-[#dce5ff]"
          @click="handleNewConversation"
        >
          <UIcon name="i-lucide-plus" class="h-5 w-5 flex-shrink-0" />
          <span>新对话</span>
        </button>
      </div>

      <!-- Conversation history -->
      <div class="mt-4 flex-1 overflow-hidden flex flex-col px-3">
        <div class="mb-2 px-1 text-xs font-medium text-zinc-400 tracking-wide">
          会话记录
        </div>

        <div v-if="conversations.length === 0" class="px-1 py-4 text-center text-xs text-zinc-400">
          暂无会话记录
        </div>

        <div v-else class="flex-1 overflow-y-auto space-y-0.5 pr-1 -mr-1">
          <div
            v-for="item in conversations"
            :key="item.thread_id"
            class="group flex items-center gap-2 rounded-xl px-2.5 py-2.5 cursor-pointer transition-colors"
            :class="
              isActiveConversation(item.thread_id)
                ? 'bg-white/90 ring-1 ring-[#d9e1ff]/60'
                : 'hover:bg-white/50'
            "
            @click="handleSelectConversation(item.thread_id)"
          >
            <UIcon
              name="i-lucide-message-circle"
              class="h-4 w-4 flex-shrink-0"
              :class="
                isActiveConversation(item.thread_id)
                  ? 'text-[#3158ff]'
                  : 'text-zinc-400'
              "
            />
            <div class="flex-1 min-w-0">
              <input
                v-if="isEditingConversation(item.thread_id)"
                :id="`conversation-rename-${item.thread_id}`"
                v-model="renameDraft"
                type="text"
                maxlength="255"
                class="w-full rounded-lg border border-[#d9e1ff] bg-white px-2 py-1 text-[13px] leading-tight text-zinc-900 outline-none ring-2 ring-[#3158ff]/10"
                @click.stop
                @blur="handleRenameBlur(item.thread_id)"
                @keydown="handleRenameKeydown($event, item.thread_id)"
              />
              <div
                v-else
                class="truncate text-[13px] leading-tight"
                :class="
                  isActiveConversation(item.thread_id)
                    ? 'text-[#3158ff] font-medium'
                    : 'text-zinc-700'
                "
              >
                {{ item.title }}
              </div>
              <div class="mt-0.5 text-[11px] text-zinc-400">
                <span v-if="isConversationBusy(item.thread_id)" class="inline-flex items-center gap-1 text-[#3158ff]">
                  <span class="h-1.5 w-1.5 rounded-full bg-[#3158ff] animate-pulse" />
                  回复中
                </span>
                <span v-else>
                  {{ formatTime(item.updated_at) }}
                </span>
              </div>
            </div>

            <!-- Actions (visible on hover) -->
            <div
              class="flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity flex gap-0.5"
              :class="isEditingConversation(item.thread_id) ? 'opacity-100' : ''"
            >
              <UButton
                v-if="!isEditingConversation(item.thread_id)"
                icon="i-lucide-pencil"
                size="xs"
                color="neutral"
                variant="ghost"
                class="text-zinc-400 hover:text-zinc-600"
                @click.stop="handleRenameConversation(item.thread_id)"
              />
              <UButton
                v-if="!isEditingConversation(item.thread_id)"
                icon="i-lucide-trash-2"
                size="xs"
                color="neutral"
                variant="ghost"
                class="text-zinc-400 hover:text-red-500"
                @click.stop="handleDeleteConversation(item.thread_id)"
              />
            </div>
          </div>
        </div>
      </div>

      <!-- Divider -->
      <div class="mx-3 my-2 border-t border-[#ebe5da]" />

      <!-- Navigation items -->
      <nav class="space-y-1 px-3 pb-4">
        <NuxtLink
          v-for="item in navItems"
          :key="item.label"
          :to="item.path"
          class="flex w-full items-center gap-3 rounded-2xl px-3 py-3 text-left text-[15px] transition-colors"
          :class="
            isActive(item.path)
              ? 'bg-[#eef2ff] text-[#3158ff] ring-1 ring-[#d9e1ff]'
              : 'text-zinc-800 hover:bg-white/70'
          "
          @click="handleNavigate()"
        >
          <UIcon :name="item.icon" class="h-5 w-5 flex-shrink-0" />
          <span class="truncate">{{ item.label }}</span>
        </NuxtLink>
      </nav>
    </aside>
  </div>
</template>
