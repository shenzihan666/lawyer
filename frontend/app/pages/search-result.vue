<script setup lang="ts">
import { storeToRefs } from "pinia";
import CaseResultPdfPreview from "../components/case-search/CaseResultPdfPreview.vue";
import { useCaseSearchStore } from "../../stores/caseSearch";

const route = useRoute();
const caseSearchStore = useCaseSearchStore();

const {
  detail,
  preview,
  previewTab,
  activeHit,
  isLoadingDetail,
  isLoadingPreview,
} = storeToRefs(caseSearchStore);

const apiOrigin = (useRuntimeConfig().public.apiBase as string).replace(
  /\/api\/v1$/,
  "",
);

const fullPreviewContent = computed(() =>
  (preview.value?.fragments ?? [])
    .map((fragment) => fragment.content?.trim())
    .filter((content): content is string => Boolean(content))
    .join("\n\n"),
);
const previewPdfUrl = computed(
  () =>
    resolveApiUrl(preview.value?.preview_url) ||
    resolveApiUrl(preview.value?.file_url),
);
const resolvedFileUrl = computed(() => resolveApiUrl(preview.value?.file_url));
const resolvedPreviewUrl = computed(() =>
  resolveApiUrl(preview.value?.preview_url),
);
const canRenderPdfPreview = computed(
  () =>
    Boolean(previewPdfUrl.value) && preview.value?.preview_status === "ready",
);
const previewViewerKey = computed(() => {
  if (!preview.value || !previewPdfUrl.value) return "case-preview";
  return `${preview.value.asset_id}:${previewPdfUrl.value}`;
});
const previewStatusText = computed(() => {
  switch (preview.value?.preview_status) {
    case "ready":
      return "PDF 预览已就绪";
    case "failed":
      return "PDF 预览生成失败";
    case "unsupported":
      return "当前文件暂不支持 PDF 预览";
    case "not_requested":
      return "PDF 预览尚未准备";
    default:
      return "正在准备 PDF 预览";
  }
});
const previewStatusHint = computed(() => {
  switch (preview.value?.preview_status) {
    case "ready":
      return "页内预览已切换到受控渲染模式，切换命中案件时会自动刷新文档。";
    case "failed":
      return "系统没能生成稳定的页内预览，请改用新窗口或下载原文件继续查看。";
    case "unsupported":
      return "当前案件文件不支持转换为 PDF 预览，仍可下载原文件核对内容。";
    case "not_requested":
      return "预览文件尚未准备完成，稍后重试或先查看结构化正文。";
    default:
      return "系统正在准备文档预览资源，请稍候片刻。";
  }
});
const previewStatusTone = computed(() => {
  switch (preview.value?.preview_status) {
    case "ready":
      return "success";
    case "failed":
      return "error";
    case "unsupported":
      return "warning";
    default:
      return "neutral";
  }
});

const searchId = computed(() => {
  const value = route.query.searchId;
  return typeof value === "string" && value ? value : null;
});

const hitId = computed(() => {
  const value = route.query.hitId;
  if (typeof value !== "string") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
});

function formatScore(score: number) {
  return score.toFixed(3);
}

function resolveApiUrl(path: string | null | undefined) {
  if (!path) return null;
  if (/^https?:\/\//.test(path)) return path;
  return `${apiOrigin}${path}`;
}

async function goBack() {
  await navigateTo("/search");
}

async function loadDetail() {
  if (!searchId.value) {
    await navigateTo("/search");
    return;
  }

  try {
    const detailPayload = await caseSearchStore.fetchDetail(searchId.value, {
      quiet: true,
    });
    const targetHitId = hitId.value ?? detailPayload.hits[0]?.id ?? null;

    if (targetHitId !== null) {
      previewTab.value = "structured";
      await caseSearchStore.selectHit(targetHitId, {
        preloaded: detailPayload,
      });
    }
  } catch {
    await navigateTo("/search");
  }
}

watch(
  [searchId, hitId],
  () => {
    void loadDetail();
  },
  { immediate: true },
);
</script>

<template>
  <div class="case-search-page px-4 py-6 md:px-8 md:py-8">
    <section class="case-search-hero">
      <div class="hero-row">
        <div>
          <p class="case-search-hero__eyebrow">Case Retrieval Desk</p>
          <h1>类案结果预览</h1>
          <p class="case-search-hero__copy">
            这里展示你在检索页选中的案件结果。结果页不会直接展开原文，只有点击某个命中案件后才会进入此页查看完整预览。
          </p>
        </div>
        <UButton
          color="neutral"
          variant="ghost"
          icon="i-lucide-arrow-left"
          @click="goBack"
        >
          返回检索页
        </UButton>
      </div>
    </section>

    <div class="case-search-layout case-search-layout--detail">
      <main class="case-panel case-panel--detail">
        <section class="case-block case-block--detail-head">
          <div class="case-block__header">
            <div>
              <p class="case-block__eyebrow">Preview</p>
              <h2>
                {{
                  activeHit?.original_filename ||
                  detail?.item.query_asset?.original_filename ||
                  "案件预览"
                }}
              </h2>
            </div>
            <div class="detail-badges">
              <UBadge v-if="detail" color="primary" variant="subtle">
                {{ detail.item.result_count }} 条案件
              </UBadge>
              <UBadge v-if="activeHit" color="warning" variant="subtle">
                {{ activeHit.matched_chunk_count }} 个命中片段
              </UBadge>
            </div>
          </div>

          <p v-if="detail" class="result-head__query">
            {{ detail.item.prepared_query }}
          </p>
          <div v-if="activeHit" class="detail-hit-meta">
            <span>#{{ activeHit.rank }}</span>
            <span>
              {{
                activeHit.matched_pages.length
                  ? `页码 ${activeHit.matched_pages.join(" / ")}`
                  : "暂无页码信息"
              }}
            </span>
            <span>score {{ formatScore(activeHit.score) }}</span>
          </div>
        </section>

        <section v-if="isLoadingDetail || isLoadingPreview" class="empty-state">
          正在整理案件预览，请稍候...
        </section>

        <section
          v-else-if="!detail || !activeHit || !preview"
          class="empty-state"
        >
          未找到可展示的预览内容，请返回结果页重新选择一个案件。
        </section>

        <section v-else-if="previewTab === 'structured'" class="preview-stack">
          <div class="mode-switcher">
            <button
              type="button"
              class="mode-switcher__item mode-switcher__item--active"
              @click="previewTab = 'structured'"
            >
              全文
            </button>
            <button
              type="button"
              class="mode-switcher__item"
              @click="previewTab = 'original'"
            >
              原 PDF
            </button>
          </div>

          <div class="preview-summary-card">
            <div class="preview-summary-card__meta">
              <span>{{ preview.original_filename }}</span>
              <span>{{ preview.file_extension }}</span>
            </div>
            <p class="preview-summary-card__excerpt">
              {{ preview.preview_excerpt }}
            </p>
          </div>

          <div class="match-chip-row">
            <span
              v-for="page in activeHit.matched_pages"
              :key="page"
              class="match-chip"
            >
              第 {{ page }} 页
            </span>
          </div>

          <article class="full-content-card">
            <h3>案件全文</h3>
            <p v-if="fullPreviewContent" class="full-content-card__body">
              {{ fullPreviewContent }}
            </p>
            <p v-else class="full-content-card__placeholder">
              当前案件暂无可用的结构化正文，请切换到“原 PDF”查看原始文档。
            </p>
          </article>
        </section>

        <section v-else class="original-preview-shell">
          <div class="mode-switcher">
            <button
              type="button"
              class="mode-switcher__item"
              @click="previewTab = 'structured'"
            >
              全文
            </button>
            <button
              type="button"
              class="mode-switcher__item mode-switcher__item--active"
              @click="previewTab = 'original'"
            >
              原 PDF
            </button>
          </div>

          <div class="original-preview-card">
            <div class="original-preview-card__status">
              <div class="original-preview-card__status-copy">
                <p class="original-preview-card__eyebrow">Viewer Status</p>
                <h3>{{ previewStatusText }}</h3>
                <p class="original-preview-card__copy">
                  {{ previewStatusHint }}
                </p>
              </div>
              <UBadge :color="previewStatusTone as any" variant="subtle">
                {{ preview.preview_status }}
              </UBadge>
            </div>
            <div class="original-preview-card__actions">
              <a
                class="preview-link"
                :href="resolvedFileUrl || '#'"
                target="_blank"
                rel="noreferrer"
              >
                下载原文件
              </a>
              <a
                v-if="resolvedPreviewUrl"
                class="preview-link preview-link--primary"
                :href="resolvedPreviewUrl || '#'"
                target="_blank"
                rel="noreferrer"
              >
                新窗口打开预览
              </a>
            </div>
          </div>

          <CaseResultPdfPreview
            v-if="canRenderPdfPreview && previewPdfUrl"
            :key="previewViewerKey"
            :source-url="previewPdfUrl"
            :title="preview.original_filename"
            :status="preview.preview_status"
          />
          <div
            v-else
            class="empty-state empty-state--flat original-preview-empty"
          >
            当前文件预览尚不可用。系统会优先展示结构化正文，你仍然可以下载原文件或在新窗口查看转换后的预览。
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
    radial-gradient(
      circle at top left,
      rgba(222, 231, 255, 0.78),
      transparent 22%
    ),
    radial-gradient(
      circle at bottom right,
      rgba(247, 229, 201, 0.72),
      transparent 28%
    ),
    linear-gradient(180deg, #f6f2ea, #fbfaf6);
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.case-search-hero,
.case-panel,
.mode-switcher,
.preview-summary-card,
.fragment-card,
.top-chunk-card,
.original-preview-card,
.full-content-card {
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
    linear-gradient(
      135deg,
      rgba(255, 255, 255, 0.95),
      rgba(250, 245, 235, 0.92)
    ),
    repeating-linear-gradient(
      -18deg,
      rgba(49, 88, 255, 0.03),
      rgba(49, 88, 255, 0.03) 1px,
      transparent 1px,
      transparent 12px
    );
}

.hero-row {
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: 16px;
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
.empty-state,
.fragment-card p,
.top-chunk-card p,
.preview-summary-card__excerpt,
.original-preview-card__copy,
.result-subtitle,
.detail-hit-meta {
  line-height: 1.75;
  color: #655f56;
}

.case-search-layout {
  display: grid;
  gap: 18px;
}

.case-panel {
  min-height: 0;
  padding: 18px;
}

.case-panel--detail {
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

.case-block__header,
.detail-hit-meta,
.preview-summary-card__meta,
.fragment-card__meta,
.top-chunk-card__meta,
.original-preview-card__actions,
.detail-badges {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.case-block__header h2 {
  color: #18181b;
}

.preview-stack,
.top-chunk-list,
.match-chip-row {
  display: grid;
  gap: 12px;
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

.preview-summary-card,
.fragment-card,
.top-chunk-card,
.original-preview-card,
.full-content-card,
.empty-state {
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.88);
}

.preview-summary-card,
.fragment-card,
.top-chunk-card,
.original-preview-card,
.full-content-card {
  padding: 14px 16px;
}

.full-content-card {
  display: grid;
  gap: 10px;
}

.full-content-card h3 {
  font-size: 0.95rem;
  font-weight: 700;
  color: #18181b;
}

.full-content-card__body {
  white-space: pre-wrap;
  line-height: 1.8;
  color: #2f2d2a;
}

.full-content-card__placeholder {
  color: #7d7569;
  line-height: 1.75;
}

.preview-summary-card__meta,
.fragment-card__meta,
.top-chunk-card__meta {
  font-size: 0.78rem;
  color: #8f877a;
}

.original-preview-card {
  display: grid;
  gap: 14px;
}

.original-preview-card__status {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.original-preview-card__status-copy {
  display: grid;
  gap: 6px;
}

.original-preview-card__eyebrow {
  font-size: 0.72rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #8f877a;
}

.original-preview-card__status-copy h3 {
  font-size: 1rem;
  font-weight: 700;
  color: #18181b;
}

.match-chip {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  background: rgba(49, 88, 255, 0.1);
  color: #3158ff;
  padding: 6px 10px;
  font-size: 0.8rem;
  font-weight: 600;
}

.fragment-card--matched {
  border-color: #bfd0ff;
  background: linear-gradient(
    180deg,
    rgba(251, 252, 255, 0.96),
    rgba(255, 255, 255, 0.9)
  );
}

.fragment-card--focused {
  border-color: #3158ff;
  box-shadow: 0 0 0 3px rgba(49, 88, 255, 0.08);
}

.preview-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 38px;
  border-radius: 999px;
  border: 1px solid #d6dce7;
  padding: 0 14px;
  color: #44506a;
  text-decoration: none;
}

.preview-link--primary {
  border-color: #3158ff;
  color: #3158ff;
}

.original-preview-shell {
  display: grid;
  gap: 12px;
  min-height: 0;
}

.original-preview-empty {
  min-height: 180px;
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
  .case-search-layout--detail {
    grid-template-columns: minmax(0, 1fr);
  }

  .case-panel--detail {
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

  .hero-row,
  .case-block__header,
  .original-preview-card__actions,
  .detail-hit-meta,
  .original-preview-card__status {
    flex-direction: column;
  }
}
</style>
