<script setup lang="ts">
import { storeToRefs } from "pinia";
import { useChatStore } from "../../stores/chat";
import { useConversationsStore } from "../../stores/conversations";
import { useDocumentStore } from "../../stores/documents";

const chatStore = useChatStore();
const conversationsStore = useConversationsStore();
const documentStore = useDocumentStore();
const toast = useToast();
const route = useRoute();

const composerRef = ref<HTMLTextAreaElement | null>(null);
const feedRef = ref<HTMLElement | null>(null);
const isComposing = ref(false);

const { documents, isLoading: isLoadingDocuments } = storeToRefs(documentStore);
const { conversations } = storeToRefs(conversationsStore);
const {
  hasAnswered,
  isResponding,
  lastAssistantMessage,
  messages,
  prompt,
  selectedDocumentIds,
  topK,
  threadId,
} = storeToRefs(chatStore);

const currentConversationTitle = computed(() => {
  if (!threadId.value) return null;
  const item = conversations.value.find((c) => c.thread_id === threadId.value);
  return item?.title ?? null;
});

const indexedDocuments = computed(() =>
  documents.value.filter((item) => item.vector_status === "indexed"),
);

const candidateOptions = computed(() =>
  indexedDocuments.value.map((item) => ({
    label: item.original_filename,
    value: item.id,
  })),
);

const selectedDocuments = computed(() =>
  indexedDocuments.value.filter((item) => selectedDocumentIds.value.includes(item.id)),
);

const visibleIndexedDocuments = computed(() => indexedDocuments.value.slice(0, 5));

const topKOptions = [3, 5, 8].map((value) => ({
  label: `${value} 条来源`,
  value,
}));

const latestMeta = computed(() => lastAssistantMessage.value?.meta ?? {});
const latestTrace = computed(() => lastAssistantMessage.value?.trace ?? null);
const latestCitationCountLabel = computed(() => {
  const count = lastAssistantMessage.value?.citations.length ?? 0;
  return `${count} 条引用`;
});
const indexedCountLabel = computed(() => `${indexedDocuments.value.length} 份已索引`);
const scopeLabel = computed(() =>
  selectedDocuments.value.length
    ? `限定 ${selectedDocuments.value.length} 份文档`
    : "检索全部已索引文档",
);

const sideSummary = computed(() => {
  if (!indexedDocuments.value.length) {
    return "先到知识库页面上传并完成向量化，聊天页才会返回带引用的回答。";
  }

  if (selectedDocuments.value.length) {
    return `当前回答将只参考选中的 ${selectedDocuments.value.length} 份文档。`;
  }

  return "当前会在全部已索引文档范围内检索答案证据。";
});

const headerStatusLabel = computed(() => {
  if (isResponding.value) {
    return "正在流式生成回答";
  }

  if (indexedDocuments.value.length) {
    return "知识库已连接";
  }

  return "等待可用知识库";
});

const headerHint = computed(() => {
  if (isResponding.value) {
    return "系统会先展示检索步骤，再把回答内容按流式逐段写入会话。";
  }

  if (hasAnswered.value) {
    return "每条回答都会保留过程步骤、引用卡片和检索元数据，方便人工核对。";
  }

  return "输入问题后，这里会按聊天流展示提问、检索步骤、回答文本和引用依据。";
});

const canSubmit = computed(
  () =>
    Boolean(prompt.value.trim()) &&
    indexedDocuments.value.length > 0 &&
    !isResponding.value,
);

function formatScore(score: number) {
  return score.toFixed(3);
}

function autoResizeComposer() {
  const element = composerRef.value;
  if (!element) return;

  element.style.height = "0px";
  element.style.height = `${Math.min(element.scrollHeight, 180)}px`;
}

function scrollFeedToBottom(behavior: ScrollBehavior = "smooth") {
  const element = feedRef.value;
  if (!element) return;

  element.scrollTo({
    top: element.scrollHeight,
    behavior,
  });
}

async function submitQuestion() {
  if (!prompt.value.trim()) {
    return;
  }

  if (!indexedDocuments.value.length) {
    toast.add({
      title: "暂无可用知识库",
      description: "请先到知识库页面上传并完成向量化。",
      color: "warning",
    });
    return;
  }

  await chatStore.ask();
  if (threadId.value) {
    conversationsStore.setActive(threadId.value);
  }
  await conversationsStore.refreshList();
  await nextTick();
  autoResizeComposer();
  scrollFeedToBottom();
}

function onPromptKeydown(event: KeyboardEvent) {
  if (event.key !== "Enter" || event.shiftKey || isComposing.value) {
    return;
  }

  event.preventDefault();

  if (!canSubmit.value) {
    return;
  }

  void submitQuestion();
}

function onPromptInput() {
  autoResizeComposer();
}

function formatTrace(trace: Record<string, unknown> | null) {
  return trace ? JSON.stringify(trace, null, 2) : "";
}

const expandedCitationSections = ref<Set<string>>(new Set());
const expandedStepSections = ref<Set<string>>(new Set());
const expandedIndividualCitations = ref<Set<string>>(new Set());

function toggleCitationSection(messageId: string) {
  if (expandedCitationSections.value.has(messageId)) {
    expandedCitationSections.value.delete(messageId);
  } else {
    expandedCitationSections.value.add(messageId);
  }
}

function isCitationSectionExpanded(messageId: string) {
  return expandedCitationSections.value.has(messageId);
}

function toggleStepSection(messageId: string) {
  if (expandedStepSections.value.has(messageId)) {
    expandedStepSections.value.delete(messageId);
  } else {
    expandedStepSections.value.add(messageId);
  }
}

function isStepSectionExpanded(messageId: string) {
  return expandedStepSections.value.has(messageId);
}

function toggleIndividualCitation(messageId: string, chunkId: string) {
  const key = `${messageId}:${chunkId}`;
  if (expandedIndividualCitations.value.has(key)) {
    expandedIndividualCitations.value.delete(key);
  } else {
    expandedIndividualCitations.value.add(key);
  }
}

function isIndividualCitationExpanded(messageId: string, chunkId: string) {
  return expandedIndividualCitations.value.has(`${messageId}:${chunkId}`);
}

watch(
  [messages, isResponding],
  async () => {
    await nextTick();
    scrollFeedToBottom();
  },
  { deep: true },
);

onMounted(async () => {
  if (!documents.value.length) {
    void documentStore.refreshDocuments();
  }

  // Handle URL param: /chat?thread=xxx
  const threadParam = route.query.thread as string | undefined;
  if (threadParam) {
    conversationsStore.setActive(threadParam);
    await chatStore.switchConversation(threadParam);
  }

  void nextTick(() => {
    autoResizeComposer();
    scrollFeedToBottom("auto");
  });
});
</script>

<template>
  <div class="chat-page px-4 py-6 md:px-8 md:py-8">
    <div class="chat-shell w-full">
      <div class="chat-workbench">
        <aside class="chat-sidebar">
          <div class="chat-sidebar__hero">
            <div class="chat-sidebar__mark">
              <UIcon name="i-lucide-scale" class="h-6 w-6" />
            </div>
          </div>


          <div class="chat-sidebar__stats">
            <div class="chat-stat">
              <span class="chat-stat__label">知识库</span>
              <strong class="chat-stat__value">{{ indexedCountLabel }}</strong>
            </div>
            <div class="chat-stat">
              <span class="chat-stat__label">当前范围</span>
              <strong class="chat-stat__value">{{ scopeLabel }}</strong>
            </div>
          </div>

          <section class="chat-panel">
            <div class="chat-panel__header">
              <div>
                <h2>检索设置</h2>
              </div>
              <UBadge color="neutral" variant="subtle" size="sm">
                {{ topK }} 条
              </UBadge>
            </div>

            <div class="space-y-4">
              <div>
                <label class="chat-field__label">参考来源数量</label>
                <USelect
                  v-model="topK"
                  :items="topKOptions"
                  value-key="value"
                  class="w-full"
                />
              </div>

              <div>
                <label class="chat-field__label">限定文档范围</label>
                <USelectMenu
                  v-model="selectedDocumentIds"
                  :items="candidateOptions"
                  value-key="value"
                  label-key="label"
                  multiple
                  searchable
                  :loading="isLoadingDocuments"
                  placeholder="默认检索全部已索引文档"
                  class="w-full"
                />
              </div>

              <p class="chat-panel__copy">{{ sideSummary }}</p>

              <div
                v-if="selectedDocuments.length"
                class="flex flex-wrap gap-2"
              >
                <UBadge
                  v-for="item in selectedDocuments.slice(0, 4)"
                  :key="item.id"
                  color="neutral"
                  variant="subtle"
                  size="xs"
                >
                  {{ item.original_filename }}
                </UBadge>
                <UBadge
                  v-if="selectedDocuments.length > 4"
                  color="neutral"
                  variant="subtle"
                  size="xs"
                >
                  +{{ selectedDocuments.length - 4 }}
                </UBadge>
              </div>
            </div>
          </section>

          <section class="chat-panel">
            <div class="chat-panel__header">
              <div>
                <h2>可用文档</h2>
              </div>
              <UBadge color="neutral" variant="subtle" size="sm">
                {{ indexedDocuments.length }}
              </UBadge>
            </div>

            <div v-if="isLoadingDocuments" class="chat-empty">
              正在加载文档列表…
            </div>
            <div v-else-if="!indexedDocuments.length" class="chat-empty">
              还没有已索引文档。请先到“知识库”页面上传并完成向量化。
            </div>
            <div v-else class="chat-doc-list">
              <article
                v-for="item in visibleIndexedDocuments"
                :key="item.id"
                class="chat-doc-item"
              >
                <div class="chat-doc-item__icon">
                  <UIcon name="i-lucide-file-text" class="h-4 w-4" />
                </div>
                <div class="min-w-0 flex-1">
                  <p class="truncate text-sm font-medium text-zinc-900">
                    {{ item.original_filename }}
                  </p>
                  <p class="mt-1 text-xs text-zinc-500">
                    {{ item.file_extension }} · {{ item.page_count || 0 }} 页
                  </p>
                </div>
              </article>
              <p
                v-if="indexedDocuments.length > visibleIndexedDocuments.length"
                class="text-xs text-zinc-500"
              >
                另有 {{ indexedDocuments.length - visibleIndexedDocuments.length }} 份已索引文档可参与问答。
              </p>
            </div>
          </section>
        </aside>

        <section class="chat-stage">
          <header class="chat-stage__header">
            <div class="min-w-0">
              <div class="status-chip">
                <span
                  class="status-dot"
                  :class="isResponding || indexedDocuments.length ? 'status-dot--live' : 'status-dot--idle'"
                />
                <span>{{ headerStatusLabel }}</span>
              </div>
              <h2 class="chat-stage__title">{{ currentConversationTitle || '法律问答会话' }}</h2>
              <p class="chat-stage__hint">{{ headerHint }}</p>
            </div>

            <div class="chat-stage__badges">
              <UBadge color="neutral" variant="subtle" size="sm">
                {{ scopeLabel }}
              </UBadge>
              <UBadge
                v-if="lastAssistantMessage?.citations.length"
                color="neutral"
                variant="subtle"
                size="sm"
              >
                {{ latestCitationCountLabel }}
              </UBadge>
              <UBadge
                v-if="latestMeta.generation_mode"
                color="primary"
                variant="subtle"
                size="sm"
              >
                {{ String(latestMeta.generation_mode) }}
              </UBadge>
              <UBadge
                v-if="latestMeta.grounding_status"
                color="warning"
                variant="subtle"
                size="sm"
              >
                {{ String(latestMeta.grounding_status) }}
              </UBadge>
            </div>
          </header>

          <div ref="feedRef" class="chat-feed">
            <div
              v-if="!messages.length"
              class="welcome-state"
            >
              <div class="welcome-state__icon">
                <UIcon name="i-lucide-message-circle-heart" class="h-10 w-10" />
              </div>
              <h3>开始一轮带引用的法律问答</h3>
              <p>
                发送问题后，页面会按聊天流展示你的提问、检索步骤、系统回答，以及每条引用对应的证据卡片。
              </p>

              <div class="welcome-prompts">
                <div class="prompt-card">
                  房屋被他人占有时，我应如何主张返还原物？
                </div>
                <div class="prompt-card">
                  合同违约责任通常需要满足哪些认定条件？
                </div>
                <div class="prompt-card">
                  劳动争议中，用人单位单方解除合同需要哪些依据？
                </div>
              </div>
            </div>

            <div v-else class="message-stack">
              <div
                v-for="message in messages"
                :key="message.id"
                class="message-row"
                :class="
                  message.role === 'user'
                    ? 'message-row--user'
                    : 'message-row--assistant'
                "
              >
                <article
                  class="message-bubble"
                  :class="
                    message.role === 'user'
                      ? 'message-bubble--user'
                      : 'message-bubble--assistant'
                  "
                >
                  <template v-if="message.role === 'user'">
                    <p class="message-role">你</p>
                    <p class="message-text">{{ message.text }}</p>
                  </template>

                  <template v-else>
                    <div class="message-bubble__meta">
                      <span class="message-role">助手</span>
                      <div class="flex flex-wrap items-center gap-2">
                        <UBadge
                          v-if="message.citations.length"
                          color="neutral"
                          variant="subtle"
                          size="xs"
                        >
                          {{ message.citations.length }} 条引用
                        </UBadge>
                        <UBadge
                          v-if="message.meta.generation_mode"
                          color="primary"
                          variant="subtle"
                          size="xs"
                        >
                          {{ String(message.meta.generation_mode) }}
                        </UBadge>
                      </div>
                    </div>

                    <div
                      v-if="message.isThinking && !message.steps.length && !message.text"
                      class="thinking-line"
                    >
                      <span class="thinking-dots" aria-hidden="true">
                        <span />
                        <span />
                        <span />
                      </span>
                      <span>正在准备检索与生成流程</span>
                    </div>

                    <div v-if="message.steps.length" class="step-section">
                      <button
                        class="step-toggle"
                        @click="toggleStepSection(message.id)"
                      >
                        <UIcon
                          :name="isStepSectionExpanded(message.id) ? 'i-lucide-chevron-up' : 'i-lucide-chevron-down'"
                          class="step-toggle__icon"
                        />
                        <span>检索过程</span>
                        <span class="step-toggle__count">{{ message.steps.length }} 步</span>
                      </button>

                      <div
                        v-show="isStepSectionExpanded(message.id)"
                        class="step-list"
                      >
                        <div
                          v-for="(step, index) in message.steps"
                          :key="`${message.id}-${index}-${step.key}`"
                          class="step-item"
                          :class="{
                            'step-item--active':
                              message.isStreaming && index === message.steps.length - 1,
                            'step-item--error': step.status === 'error',
                          }"
                        >
                          <span class="step-index">{{ index + 1 }}</span>
                          <div class="min-w-0">
                            <p class="step-label">{{ step.label }}</p>
                            <p v-if="step.detail" class="step-detail">
                              {{ step.detail }}
                            </p>
                          </div>
                        </div>
                      </div>
                    </div>

                    <p v-if="message.text" class="message-text">
                      {{ message.text }}
                    </p>

                    <div
                      v-if="message.error"
                      class="message-note message-note--error"
                    >
                      {{ message.error }}
                    </div>

                    <div
                      v-else-if="message.meta.answer_generation_skipped_reason"
                      class="message-note"
                    >
                      当前为兜底模式：{{
                        String(message.meta.answer_generation_skipped_reason)
                      }}
                    </div>

                    <div
                      v-if="message.citations.length"
                      class="citation-section"
                    >
                      <button
                        class="citation-toggle"
                        @click="toggleCitationSection(message.id)"
                      >
                        <UIcon
                          :name="isCitationSectionExpanded(message.id) ? 'i-lucide-chevron-up' : 'i-lucide-chevron-down'"
                          class="citation-toggle__icon"
                        />
                        <span>{{ message.citations.length }} 条引用</span>
                      </button>

                      <div
                        v-show="isCitationSectionExpanded(message.id)"
                        class="citation-list"
                      >
                        <article
                          v-for="citation in message.citations"
                          :key="citation.chunk_id"
                          class="citation-card"
                        >
                          <button
                            class="citation-card__toggle"
                            @click="toggleIndividualCitation(message.id, citation.chunk_id)"
                          >
                            <div class="min-w-0 flex-1">
                              <div class="flex flex-wrap items-center gap-2">
                                <UBadge color="primary" variant="subtle" size="xs">
                                  [{{ citation.citation_number }}]
                                </UBadge>
                                <p class="citation-card__title">
                                  {{ citation.original_filename }}
                                </p>
                              </div>

                              <div class="citation-card__meta">
                                <span class="citation-chip">
                                  L{{ citation.chunk_level }} / #{{ citation.chunk_index }}
                                </span>
                                <span class="citation-chip">
                                  第 {{ citation.page_number || 0 }} 页
                                </span>
                                <span class="citation-chip mono">
                                  score {{ formatScore(citation.score) }}
                                </span>
                              </div>
                            </div>

                            <div class="flex items-center gap-2">
                              <span class="citation-chip mono">
                                {{ citation.chunk_id }}
                              </span>
                              <UIcon
                                :name="isIndividualCitationExpanded(message.id, citation.chunk_id) ? 'i-lucide-chevron-up' : 'i-lucide-chevron-down'"
                                class="citation-card__expand-icon"
                              />
                            </div>
                          </button>

                          <div
                            v-show="isIndividualCitationExpanded(message.id, citation.chunk_id)"
                            class="citation-snippet-wrapper"
                          >
                            <p class="citation-snippet">{{ citation.snippet }}</p>
                          </div>
                        </article>
                      </div>
                    </div>

                    <details
                      v-if="message.trace"
                      class="trace-panel"
                    >
                      <summary>查看检索元数据</summary>
                      <pre>{{ formatTrace(message.trace) }}</pre>
                    </details>
                  </template>
                </article>
              </div>
            </div>
          </div>

          <footer class="composer-shell">
            <div class="composer-shell__meta">
              <span>{{ scopeLabel }}</span>
              <span>Enter 发送，Shift + Enter 换行</span>
            </div>

            <div class="composer">
              <div class="composer__prefix">
                <UIcon name="i-lucide-message-circle-more" class="h-5 w-5" />
              </div>

              <textarea
                ref="composerRef"
                v-model="prompt"
                rows="1"
                placeholder="输入法律问题，例如：房屋被他人占有时，我应如何主张返还原物？"
                @keydown="onPromptKeydown"
                @input="onPromptInput"
                @compositionstart="isComposing = true"
                @compositionend="isComposing = false"
              />

              <UButton
                color="primary"
                class="composer__send"
                :loading="isResponding"
                :disabled="!canSubmit"
                @click="submitQuestion"
              >
                发送
              </UButton>
            </div>
          </footer>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat-page {
  min-height: 100vh;
  background:
    radial-gradient(circle at top left, rgba(221, 228, 255, 0.7), transparent 28%),
    radial-gradient(circle at bottom right, rgba(244, 234, 216, 0.82), transparent 30%),
    #fcfbf8;
}

.chat-shell {
  min-height: 0;
}

.chat-workbench {
  display: grid;
  gap: 24px;
  align-items: stretch;
  min-height: 0;
}

.chat-sidebar {
  display: flex;
  flex-direction: column;
  gap: 18px;
  border-radius: 32px;
  border: 1px solid #ebe5da;
  background: linear-gradient(180deg, rgba(247, 244, 238, 0.98), rgba(255, 255, 255, 0.94));
  padding: 24px;
  box-shadow: 0 20px 60px rgba(34, 24, 12, 0.06);
  min-height: 0;
}

.chat-sidebar__hero {
  display: flex;
  align-items: center;
  gap: 14px;
}

.chat-sidebar__mark {
  display: flex;
  height: 56px;
  width: 56px;
  align-items: center;
  justify-content: center;
  border-radius: 18px;
  background: linear-gradient(135deg, #eef2ff, #ffffff);
  color: #3158ff;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9);
}

.chat-sidebar__stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.chat-stat {
  border-radius: 22px;
  border: 1px solid #ece6dc;
  background: rgba(255, 255, 255, 0.82);
  padding: 14px 16px;
}

.chat-stat__label {
  display: block;
  font-size: 12px;
  color: #71717a;
}

.chat-stat__value {
  display: block;
  margin-top: 8px;
  font-size: 0.98rem;
  font-weight: 700;
  line-height: 1.5;
  color: #18181b;
}

.chat-panel {
  border-radius: 24px;
  border: 1px solid #ece6dc;
  background: rgba(255, 255, 255, 0.96);
  padding: 18px;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.92);
}

.chat-panel__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.chat-panel__header h2 {
  font-size: 1rem;
  font-weight: 600;
  color: #18181b;
}

.chat-panel__header p,
.chat-panel__copy {
  margin-top: 4px;
  font-size: 0.86rem;
  line-height: 1.65;
  color: #71717a;
}

.chat-field__label {
  display: block;
  margin-bottom: 8px;
  font-size: 0.88rem;
  font-weight: 600;
  color: #3f3f46;
}

.chat-empty {
  border-radius: 20px;
  border: 1px dashed #e7e1d6;
  background: #fcfbf8;
  padding: 16px;
  font-size: 0.88rem;
  line-height: 1.7;
  color: #71717a;
}

.chat-doc-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.chat-doc-item {
  display: flex;
  align-items: center;
  gap: 12px;
  border-radius: 18px;
  border: 1px solid #eee7db;
  background: #fcfbf8;
  padding: 12px 13px;
}

.chat-doc-item__icon {
  display: flex;
  height: 34px;
  width: 34px;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  background: #ffffff;
  color: #3158ff;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.92);
}

.chat-stage {
  display: flex;
  min-height: calc(100vh - 4rem);
  flex-direction: column;
  overflow: hidden;
  border-radius: 32px;
  border: 1px solid #ebe5da;
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 20px 60px rgba(34, 24, 12, 0.06);
  backdrop-filter: blur(12px);
  min-height: 0;
}

.chat-stage__header {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  border-bottom: 1px solid #ebe5da;
  padding: 22px 24px;
}

.status-chip {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  border-radius: 999px;
  background: #f7f4ee;
  padding: 8px 12px;
  font-size: 0.84rem;
  font-weight: 600;
  color: #3f3f46;
}

.status-dot {
  height: 10px;
  width: 10px;
  border-radius: 999px;
}

.status-dot--live {
  background: #3158ff;
  box-shadow: 0 0 0 4px rgba(49, 88, 255, 0.14);
}

.status-dot--idle {
  background: #b7b0a4;
}

.chat-stage__title {
  margin-top: 14px;
  font-size: 1.65rem;
  font-weight: 700;
  letter-spacing: -0.03em;
  color: #18181b;
}

.chat-stage__hint {
  margin-top: 6px;
  max-width: 720px;
  font-size: 0.92rem;
  line-height: 1.7;
  color: #71717a;
}

.chat-stage__badges {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.chat-feed {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 28px 24px 20px;
  background:
    linear-gradient(180deg, rgba(252, 251, 248, 0.88), rgba(252, 251, 248, 0.52)),
    radial-gradient(circle at top center, rgba(238, 242, 255, 0.55), transparent 24%);
}

.welcome-state {
  margin: auto;
  max-width: 680px;
  text-align: center;
}

.welcome-state__icon {
  display: inline-flex;
  height: 96px;
  width: 96px;
  align-items: center;
  justify-content: center;
  border-radius: 30px;
  background: linear-gradient(135deg, #ffffff, #f7f4ee);
  color: #3158ff;
  box-shadow: 0 18px 40px rgba(34, 24, 12, 0.08);
}

.welcome-state h3 {
  margin-top: 24px;
  font-size: 2rem;
  font-weight: 700;
  letter-spacing: -0.04em;
  color: #18181b;
}

.welcome-state p {
  margin-top: 10px;
  font-size: 0.96rem;
  line-height: 1.8;
  color: #71717a;
}

.welcome-prompts {
  margin-top: 24px;
  display: grid;
  gap: 12px;
  text-align: left;
}

.prompt-card {
  border-radius: 20px;
  border: 1px solid #ece6dc;
  background: rgba(255, 255, 255, 0.92);
  padding: 16px 18px;
  font-size: 0.94rem;
  line-height: 1.7;
  color: #3f3f46;
}

.message-stack {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.message-row {
  display: flex;
}

.message-row--user {
  justify-content: flex-end;
}

.message-row--assistant {
  justify-content: flex-start;
}

.message-bubble {
  max-width: min(860px, 88%);
  border-radius: 26px;
  padding: 18px 20px;
  box-shadow: 0 10px 24px rgba(34, 24, 12, 0.05);
}

.message-bubble--assistant {
  border: 1px solid #ece6dc;
  border-bottom-left-radius: 10px;
  background: #ffffff;
}

.message-bubble--user {
  border-bottom-right-radius: 10px;
  background: linear-gradient(135deg, #3158ff, #5f7eff);
  color: #ffffff;
}

.message-bubble__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.message-role {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: #71717a;
}

.message-bubble--user .message-role {
  color: rgba(255, 255, 255, 0.75);
}

.message-text {
  white-space: pre-wrap;
  font-size: 0.95rem;
  line-height: 1.9;
  color: #3f3f46;
}

.message-bubble--user .message-text {
  color: #ffffff;
}

.thinking-line {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.95rem;
  font-weight: 600;
  color: #18181b;
}

.thinking-dots {
  display: inline-flex;
  gap: 4px;
}

.thinking-dots span {
  height: 7px;
  width: 7px;
  border-radius: 999px;
  background: #3158ff;
  animation: thinking-bounce 1.4s infinite ease-in-out both;
}

.thinking-dots span:nth-child(1) {
  animation-delay: -0.32s;
}

.thinking-dots span:nth-child(2) {
  animation-delay: -0.16s;
}

.step-section {
  margin-bottom: 14px;
}

.step-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: none;
  background: none;
  padding: 6px 10px;
  border-radius: 12px;
  font-size: 0.84rem;
  font-weight: 600;
  color: #71717a;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.step-toggle:hover {
  background: #f4f2ee;
  color: #3f3f46;
}

.step-toggle__icon {
  height: 16px;
  width: 16px;
  transition: transform 0.2s;
}

.step-toggle__count {
  font-size: 0.76rem;
  font-weight: 500;
  color: #a1a1aa;
}

.step-list {
  margin-top: 10px;
  display: grid;
  gap: 10px;
}

.step-item {
  display: flex;
  gap: 12px;
  border-radius: 18px;
  border: 1px solid #ece6dc;
  background: #fcfbf8;
  padding: 12px 13px;
}

.step-item--active {
  border-color: #dbe3ff;
  background: linear-gradient(180deg, #fcfbff, #fcfbf8);
}

.step-item--error {
  border-color: #f4c8c8;
  background: #fff7f7;
}

.step-index {
  display: inline-flex;
  height: 24px;
  width: 24px;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: #eef2ff;
  font-size: 0.75rem;
  font-weight: 700;
  color: #3158ff;
}

.step-item--error .step-index {
  background: #fde8e8;
  color: #b42318;
}

.step-label {
  font-size: 0.88rem;
  font-weight: 600;
  color: #18181b;
}

.step-detail {
  margin-top: 4px;
  font-size: 0.82rem;
  line-height: 1.65;
  color: #71717a;
}

.message-note {
  margin-top: 14px;
  border-radius: 18px;
  border: 1px solid #eadfcb;
  background: #fff8ec;
  padding: 12px 14px;
  font-size: 0.88rem;
  line-height: 1.7;
  color: #8a5a14;
}

.message-note--error {
  border-color: #f4c8c8;
  background: #fff7f7;
  color: #b42318;
}

.citation-section {
  margin-top: 18px;
}

.citation-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: none;
  background: none;
  padding: 6px 10px;
  border-radius: 12px;
  font-size: 0.84rem;
  font-weight: 600;
  color: #71717a;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.citation-toggle:hover {
  background: #f4f2ee;
  color: #3f3f46;
}

.citation-toggle__icon {
  height: 16px;
  width: 16px;
  transition: transform 0.2s;
}

.citation-list {
  margin-top: 10px;
  display: grid;
  gap: 12px;
}

.citation-card__title {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.95rem;
  font-weight: 600;
  color: #18181b;
}

.citation-card__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 9px;
}

.citation-chip {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  background: #ffffff;
  padding: 5px 10px;
  font-size: 0.78rem;
  color: #52525b;
  box-shadow: inset 0 0 0 1px #e7e1d6;
}

.citation-chip.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
}

.citation-card {
  border-radius: 20px;
  border: 1px solid #ece6dc;
  background: #fcfbf8;
  padding: 0;
  overflow: hidden;
}

.citation-card__toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  border: none;
  background: none;
  padding: 14px 15px;
  cursor: pointer;
  text-align: left;
  transition: background 0.15s;
}

.citation-card__toggle:hover {
  background: rgba(0, 0, 0, 0.02);
}

.citation-card__expand-icon {
  height: 16px;
  width: 16px;
  color: #a1a1aa;
  flex-shrink: 0;
  transition: transform 0.2s;
}

.citation-snippet-wrapper {
  border-top: 1px solid #ece6dc;
  background: rgba(255, 255, 255, 0.6);
}

.citation-snippet {
  padding: 14px 15px;
  white-space: pre-wrap;
  font-size: 0.9rem;
  line-height: 1.8;
  color: #52525b;
}

.trace-panel {
  margin-top: 16px;
  border-radius: 18px;
  border: 1px solid #ece6dc;
  background: #fcfbf8;
  padding: 12px 14px;
}

.trace-panel summary {
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: 600;
  color: #3f3f46;
}

.trace-panel pre {
  margin-top: 12px;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 0.78rem;
  line-height: 1.6;
  color: #52525b;
}

.composer-shell {
  border-top: 1px solid #ebe5da;
  background: rgba(255, 255, 255, 0.96);
  padding: 18px 24px 22px;
}

.composer-shell__meta {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  font-size: 0.76rem;
  color: #71717a;
}

.composer {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  border-radius: 28px;
  border: 1px solid #e7e1d6;
  background: #fcfbf8;
  padding: 12px;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9);
}

.composer:focus-within {
  border-color: #cfd8ff;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.9),
    0 0 0 4px rgba(49, 88, 255, 0.08);
}

.composer__prefix {
  display: flex;
  height: 44px;
  width: 44px;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  border: 1px solid #ebe5da;
  background: #ffffff;
  color: #3158ff;
}

.composer textarea {
  min-height: 52px;
  max-height: 180px;
  flex: 1;
  resize: none;
  border: none;
  background: transparent;
  padding: 10px 0;
  font-size: 0.96rem;
  line-height: 1.8;
  color: #18181b;
  outline: none;
}

.composer textarea::placeholder {
  color: #a1a1aa;
}

.composer__send {
  min-height: 52px;
  border-radius: 999px;
}

@keyframes thinking-bounce {
  0%,
  80%,
  100% {
    transform: scale(0.6);
    opacity: 0.35;
  }

  40% {
    transform: scale(1);
    opacity: 1;
  }
}

@media (min-width: 1280px) {
  .chat-page {
    height: 100dvh;
    overflow: hidden;
  }

  .chat-shell {
    height: 100%;
  }

  .chat-workbench {
    height: 100%;
    grid-template-columns: 340px minmax(0, 1fr);
  }

  .chat-sidebar {
    overflow-y: auto;
  }

  .chat-stage {
    height: 100%;
    min-height: 0;
  }
}

@media (max-width: 1279px) {
  .chat-sidebar {
    order: 2;
  }

  .chat-stage {
    order: 1;
    min-height: 72vh;
  }
}

@media (max-width: 767px) {
  .chat-sidebar,
  .chat-stage {
    border-radius: 26px;
  }

  .chat-stage__header,
  .chat-feed,
  .composer-shell {
    padding-left: 18px;
    padding-right: 18px;
  }

  .message-bubble {
    max-width: 100%;
  }

  .welcome-state h3 {
    font-size: 1.6rem;
  }

  .chat-sidebar__stats {
    grid-template-columns: 1fr;
  }
}
</style>
