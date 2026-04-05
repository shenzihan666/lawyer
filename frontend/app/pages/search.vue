<script setup lang="ts">
import { storeToRefs } from "pinia";
import { useCaseSearchStore } from "../../stores/caseSearch";
import { useDocumentStore } from "../../stores/documents";

const documentStore = useDocumentStore();
const caseSearchStore = useCaseSearchStore();

const { documents, isLoading: isLoadingDocuments } = storeToRefs(documentStore);
const {
  mode,
  queryText,
  pendingFile,
  topK,
  selectedDocumentIds,
  searches,
  detail,
  activeSearchId,
  isCreating,
  isLoadingHistory,
} = storeToRefs(caseSearchStore);

const indexedDocuments = computed(() =>
  documents.value.filter((item) => item.vector_status === "indexed"),
);

const candidateOptions = computed(() =>
  indexedDocuments.value.map((item) => ({
    label: item.original_filename,
    value: item.id,
  })),
);

const topKOptions = [3, 5, 8, 10].map((value) => ({
  label: `${value} 条案件`,
  value,
}));

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatScore(score: number) {
  return score.toFixed(3);
}

function formatFileSize(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  caseSearchStore.setPendingFile(input.files?.[0] ?? null);
  input.value = "";
}

async function handleSelectHistory(searchId: string) {
  await caseSearchStore.selectSearch(searchId);
}

async function handleSelectHit(hitId: number) {
  if (!detail.value) return;
  await navigateTo({
    path: "/search-result",
    query: {
      searchId: detail.value.item.id,
      hitId: String(hitId),
    },
  });
}

onMounted(async () => {
  if (!documents.value.length) {
    await documentStore.refreshDocuments();
  }
  const items = await caseSearchStore.fetchHistory();
  const firstItem = items[0];
  if (!detail.value && firstItem) {
    await caseSearchStore.fetchDetail(firstItem.id, { quiet: true });
  }
});
</script>

<template>
  <div class="case-search-page px-4 py-6 md:px-8 md:py-8">
    <section class="case-search-hero">
      <div>
        <p class="case-search-hero__eyebrow">Case Retrieval Desk</p>
        <h1>类案检索</h1>
      </div>
    </section>

    <div class="case-search-layout">
      <aside class="case-panel case-panel--sidebar">
        <section class="case-block">
          <div class="case-block__header">
            <div>
              <p class="case-block__eyebrow">Launch</p>
              <h2>发起检索</h2>
            </div>
            <UBadge color="neutral" variant="subtle" size="sm">
              {{ topK }} 条
            </UBadge>
          </div>

          <div class="mode-switcher">
            <button
              type="button"
              class="mode-switcher__item"
              :class="{ 'mode-switcher__item--active': mode === 'text' }"
              @click="mode = 'text'"
            >
              描述案件
            </button>
            <button
              type="button"
              class="mode-switcher__item"
              :class="{ 'mode-switcher__item--active': mode === 'upload' }"
              @click="mode = 'upload'"
            >
              上传案件
            </button>
          </div>

          <div v-if="mode === 'text'" class="field-stack">
            <label class="field-label">案件描述</label>
            <textarea
              v-model="queryText"
              rows="8"
              class="case-textarea"
              placeholder="例如：买卖合同履行过程中，买方主张卖方逾期交付并要求解除合同与赔偿违约损失。"
            />
          </div>

          <div v-else class="field-stack">
            <label class="upload-dropzone">
              <input type="file" class="hidden" accept=".pdf,.docx,.xls,.xlsx" @change="onFileChange" />
              <UIcon name="i-lucide-file-up" class="h-8 w-8 text-[#3158ff]" />
              <div>
                <p class="upload-dropzone__title">上传待比对案件</p>
                <p class="upload-dropzone__copy">支持 PDF、Word、Excel。</p>
              </div>
            </label>

            <div v-if="pendingFile" class="pending-file-card">
              <div>
                <p class="pending-file-card__title">{{ pendingFile.name }}</p>
                <p class="pending-file-card__meta">{{ formatFileSize(pendingFile.size) }}</p>
              </div>
              <UButton icon="i-lucide-x" color="neutral" variant="ghost" size="xs" @click="caseSearchStore.setPendingFile(null)" />
            </div>
          </div>

          <div class="field-stack">
            <label class="field-label">返回数量</label>
            <USelect v-model="topK" :items="topKOptions" value-key="value" class="w-full" />
          </div>

          <div class="field-stack">
            <label class="field-label">限定知识库范围</label>
            <USelectMenu
              v-model="selectedDocumentIds"
              :items="candidateOptions"
              value-key="value"
              label-key="label"
              multiple
              searchable
              :loading="isLoadingDocuments"
              placeholder="默认搜索全部已索引案件"
              class="w-full"
            />
          </div>

          <div class="case-actions">
            <UButton color="neutral" variant="ghost" @click="caseSearchStore.resetComposer()">清空</UButton>
            <UButton color="primary" :loading="isCreating" @click="caseSearchStore.createSearch()">开始检索</UButton>
          </div>
        </section>

        <section class="case-block case-block--history">
          <div class="case-block__header">
            <div>
              <p class="case-block__eyebrow">History</p>
              <h2>检索历史</h2>
            </div>
            <UButton
              icon="i-lucide-refresh-cw"
              color="neutral"
              variant="ghost"
              size="xs"
              :loading="isLoadingHistory"
              @click="caseSearchStore.fetchHistory()"
            />
          </div>

          <div v-if="!searches.length" class="empty-state">
            还没有类案检索历史。首次检索后，这里会保存文本查询或上传文件记录。
          </div>

          <div v-else class="history-list">
            <button
              v-for="item in searches"
              :key="item.id"
              class="history-card"
              :class="{ 'history-card--active': activeSearchId === item.id }"
              @click="handleSelectHistory(item.id)"
            >
              <div class="history-card__header">
                <div>
                  <p class="history-card__title">
                    {{ item.query_type === 'upload' ? item.query_asset?.original_filename || '上传案件' : item.query_text || '文本检索' }}
                  </p>
                  <p class="history-card__meta">{{ formatDate(item.created_at) }}</p>
                </div>
                <UBadge color="neutral" variant="subtle" size="xs">
                  {{ item.result_count }} 条
                </UBadge>
              </div>
              <p class="history-card__summary">
                {{ item.prepared_query }}
              </p>
            </button>
          </div>
        </section>
      </aside>

      <main class="case-panel case-panel--results">
        <section class="case-block case-block--results-head">
          <div class="case-block__header">
            <div>
              <p class="case-block__eyebrow">Results</p>
              <h2>{{ detail?.item.query_type === 'upload' ? '上传案件命中结果' : '文本案件命中结果' }}</h2>
            </div>
            <div class="result-head__meta">
              <UBadge v-if="detail" color="primary" variant="subtle">{{ detail.item.result_count }} 条案件</UBadge>
              <UBadge v-if="detail?.item.query_asset" color="neutral" variant="subtle">
                {{ detail.item.query_asset.original_filename }}
              </UBadge>
            </div>
          </div>
          <p v-if="detail" class="result-head__query">{{ detail.item.prepared_query }}</p>
          <div v-else class="empty-state empty-state--flat">
            发起一次类案检索后，这里会展示案件级结果列表与命中摘要。
          </div>
        </section>

        <section v-if="detail" class="result-stack">
          <article
            v-for="hit in detail.hits"
            :key="hit.id"
            class="result-card"
            @click="handleSelectHit(hit.id)"
          >
            <div class="result-card__header">
              <div>
                <div class="result-card__topline">
                  <span class="result-rank">#{{ hit.rank }}</span>
                  <p class="result-title">{{ hit.original_filename }}</p>
                </div>
                <p class="result-subtitle">
                  命中 {{ hit.matched_chunk_count }} 个片段
                  <span v-if="hit.matched_pages.length"> · 页码 {{ hit.matched_pages.join(' / ') }}</span>
                </p>
              </div>
              <div class="score-pill">{{ formatScore(hit.score) }}</div>
            </div>

            <div class="snippet-list">
              <p v-for="snippet in hit.matched_snippets" :key="snippet" class="snippet-pill">
                {{ snippet }}
              </p>
            </div>

            <div class="top-chunk-list">
              <div v-for="chunk in hit.top_chunks" :key="chunk.chunk_id" class="top-chunk-card">
                <div class="top-chunk-card__meta">
                  <span>{{ chunk.page_number ? `第 ${chunk.page_number} 页` : '未分页' }}</span>
                  <span>score {{ formatScore(chunk.score) }}</span>
                </div>
                <p>{{ chunk.content }}</p>
              </div>
            </div>
          </article>

          <div v-if="!detail.hits.length" class="empty-state">
            本次没有找到相似案件。你可以尝试补充争议焦点、案由、责任认定或放宽知识库范围。
          </div>
        </section>
      </main>
    </div>
  </div>
</template>

<style scoped>
.case-search-page {
  min-height: 100vh;
  background:
    radial-gradient(circle at top left, rgba(222, 231, 255, 0.78), transparent 22%),
    radial-gradient(circle at bottom right, rgba(247, 229, 201, 0.72), transparent 28%),
    linear-gradient(180deg, #f6f2ea, #fbfaf6);
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.case-search-hero,
.case-panel,
.mode-switcher,
.history-card,
.result-card,
.preview-summary-card,
.fragment-card,
.top-chunk-card,
.upload-dropzone,
.pending-file-card,
.original-preview-card {
  border: 1px solid #e9e0d0;
  box-shadow: 0 20px 48px rgba(34, 24, 12, 0.06);
}

.case-search-hero,
.case-panel {
  border-radius: 32px;
  background: rgba(255, 255, 255, 0.86);
}

.case-search-hero {
  display: grid;
  gap: 18px;
  padding: 26px 28px;
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.95), rgba(250, 245, 235, 0.92)),
    repeating-linear-gradient(
      -18deg,
      rgba(49, 88, 255, 0.03),
      rgba(49, 88, 255, 0.03) 1px,
      transparent 1px,
      transparent 12px
    );
}

.case-search-hero__eyebrow,
.case-block__eyebrow {
  font-size: 11px;
  letter-spacing: 0.24em;
  text-transform: uppercase;
  color: #8f877a;
}

.case-search-hero h1 {
  margin-top: 10px;
  font-size: clamp(2rem, 3vw, 3.25rem);
  line-height: 0.96;
  letter-spacing: -0.05em;
  color: #18181b;
}

.case-search-hero__copy,
.result-head__query,
.history-card__summary,
.empty-state,
.fragment-card p,
.top-chunk-card p,
.preview-summary-card__excerpt,
.original-preview-card__copy,
.upload-dropzone__copy,
.result-subtitle {
  line-height: 1.75;
  color: #655f56;
}

.case-search-hero__copy {
  margin-top: 12px;
  max-width: 860px;
}

.case-search-layout {
  display: grid;
  gap: 18px;
}

.case-panel {
  min-height: 0;
  padding: 18px;
}

.case-panel--sidebar,
.case-panel--results {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.case-block {
  border-radius: 26px;
  background: rgba(255, 255, 255, 0.72);
  padding: 18px;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9);
}

.case-block--history,
.case-panel--results {
  min-height: 0;
}

.case-block__header,
.case-actions,
.result-card__header,
.result-head__meta,
.history-card__header,
.preview-summary-card__meta,
.fragment-card__meta,
.top-chunk-card__meta,
.original-preview-card__actions {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.case-block__header h2,
.result-title {
  color: #18181b;
}

.mode-switcher {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  border-radius: 22px;
  padding: 8px;
  background: rgba(247, 243, 236, 0.96);
}

.mode-switcher__item {
  appearance: none;
  border: 1px solid transparent;
  border-radius: 16px;
  background: transparent;
  padding: 12px 14px;
  font-weight: 600;
  color: #665f56;
  transition: 0.18s ease;
}

.mode-switcher__item--active {
  border-color: #3158ff;
  background: rgba(243, 247, 255, 0.92);
  color: #3158ff;
}

.field-stack,
.result-stack,
.history-list,
.top-chunk-list,
.snippet-list {
  display: grid;
  gap: 12px;
}

.field-label {
  font-size: 0.85rem;
  font-weight: 600;
  color: #433f39;
}

.case-textarea {
  width: 100%;
  border: 1px solid #e5dccd;
  border-radius: 22px;
  background: #fffdf9;
  padding: 15px 16px;
  font-size: 0.94rem;
  line-height: 1.8;
  color: #18181b;
  resize: vertical;
  min-height: 180px;
  outline: none;
}

.case-textarea:focus {
  border-color: #3158ff;
  box-shadow: 0 0 0 4px rgba(49, 88, 255, 0.08);
}

.upload-dropzone,
.pending-file-card,
.preview-summary-card,
.fragment-card,
.top-chunk-card,
.original-preview-card,
.history-card,
.result-card {
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.88);
}

.upload-dropzone {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 18px;
  cursor: pointer;
  background: rgba(255, 249, 240, 0.92);
}

.upload-dropzone__title,
.pending-file-card__title,
.history-card__title {
  font-size: 0.95rem;
  font-weight: 600;
  color: #18181b;
}

.pending-file-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 14px 16px;
}

.pending-file-card__meta,
.history-card__meta,
.result-rank,
.result-subtitle,
.fragment-card__meta,
.top-chunk-card__meta {
  font-size: 0.78rem;
  color: #8f877a;
}

.history-list,
.result-stack,
.preview-stack {
  max-height: calc(100vh - 24rem);
  overflow-y: auto;
  padding-right: 4px;
}

.history-card,
.result-card {
  padding: 16px;
  text-align: left;
  transition: 0.18s ease;
}

.history-card--active,
.result-card--active,
.fragment-card--matched {
  border-color: #bfd0ff;
  background: linear-gradient(180deg, rgba(251, 252, 255, 0.96), rgba(255, 255, 255, 0.9));
}

.result-card {
  cursor: pointer;
}

.result-card__topline {
  display: flex;
  align-items: center;
  gap: 10px;
}

.result-rank {
  border-radius: 999px;
  background: rgba(49, 88, 255, 0.1);
  padding: 4px 8px;
  color: #3158ff;
  font-weight: 700;
}

.result-title {
  font-size: 1rem;
  font-weight: 700;
}

.score-pill,
.match-chip,
.snippet-pill {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
}

.score-pill {
  background: #18181b;
  color: #fff;
  padding: 8px 10px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 0.82rem;
}

.snippet-pill {
  background: rgba(250, 245, 235, 0.98);
  padding: 10px 12px;
  font-size: 0.86rem;
}

.top-chunk-card,
.fragment-card {
  padding: 14px 16px;
}

.fragment-card--focused {
  border-color: #3158ff;
  box-shadow: 0 0 0 3px rgba(49, 88, 255, 0.08);
}

.empty-state {
  border: 1px dashed #ded3c2;
  border-radius: 24px;
  padding: 20px;
  background: rgba(255, 249, 241, 0.7);
}

.empty-state--flat {
  min-height: 96px;
}

@media (min-width: 1100px) {
  .case-search-hero {
    align-items: start;
  }

  .case-search-layout {
    grid-template-columns: 320px minmax(0, 1fr);
    align-items: start;
  }

  .case-panel--sidebar,
  .case-panel--results {
    position: sticky;
    top: 24px;
    max-height: calc(100vh - 48px);
  }
}

@media (max-width: 767px) {
  .case-search-page {
    padding-bottom: 28px;
  }

  .case-search-hero,
  .case-panel {
    border-radius: 26px;
    padding: 18px;
  }
}
</style>
