<script setup lang="ts">
import VuePdfEmbed from "vue-pdf-embed";
import "vue-pdf-embed/dist/styles/annotationLayer.css";
import "vue-pdf-embed/dist/styles/textLayer.css";

type RenderPhase = "loading" | "ready" | "failed";

const props = withDefaults(
  defineProps<{
    sourceUrl: string;
    title?: string;
    status?: string;
  }>(),
  {
    title: "PDF Preview",
    status: "ready",
  },
);

const renderPhase = ref<RenderPhase>("loading");
const errorMessage = ref("");
const progressLabel = ref("正在加载 PDF 预览...");
const pdfSource = shallowRef<Uint8Array | null>(null);
let activeController: AbortController | null = null;

const canRender = computed(
  () => props.status === "ready" && props.sourceUrl.trim().length > 0,
);

watch(
  () => [props.sourceUrl, props.status],
  async () => {
    activeController?.abort();
    pdfSource.value = null;
    errorMessage.value = "";
    progressLabel.value = "正在加载 PDF 预览...";

    if (!canRender.value) {
      renderPhase.value = "failed";
      return;
    }

    renderPhase.value = "loading";
    const controller = new AbortController();
    activeController = controller;

    try {
      const response = await fetch(props.sourceUrl, {
        signal: controller.signal,
      });
      if (!response.ok) {
        throw new Error(`PDF 下载失败 (${response.status})`);
      }
      const buffer = await response.arrayBuffer();
      if (controller.signal.aborted) return;
      pdfSource.value = new Uint8Array(buffer);
      progressLabel.value = "PDF 已加载，正在渲染页面...";
    } catch (error) {
      if (controller.signal.aborted) return;
      renderPhase.value = "failed";
      errorMessage.value =
        error instanceof Error
          ? error.message
          : "PDF 文件加载失败，请改用新窗口查看。";
    }
  },
  { immediate: true },
);

onBeforeUnmount(() => {
  activeController?.abort();
});

function handleLoaded(_document: unknown) {
  renderPhase.value = "loading";
  errorMessage.value = "";
}

function handleProgress(progress: { loaded: number; total?: number }) {
  if (!progress.total) {
    progressLabel.value = "正在加载 PDF 预览...";
    return;
  }

  const percent = Math.min(
    100,
    Math.max(1, Math.round((progress.loaded / progress.total) * 100)),
  );
  progressLabel.value = `正在加载 PDF 预览... ${percent}%`;
}

function handleRendered() {
  renderPhase.value = "ready";
  errorMessage.value = "";
}

function handleFailed(error: Error) {
  renderPhase.value = "failed";
  errorMessage.value = error.message || "PDF 预览渲染失败，请改用新窗口查看。";
}
</script>

<template>
  <div class="pdf-preview-shell">
    <ClientOnly>
      <div
        v-if="canRender && renderPhase !== 'failed'"
        class="pdf-preview-stage"
        :aria-busy="renderPhase === 'loading'"
      >
        <div v-if="renderPhase === 'loading'" class="pdf-preview-loading">
          <span class="pdf-preview-loading__spinner" />
          <p>{{ progressLabel }}</p>
        </div>

        <VuePdfEmbed
          v-if="pdfSource"
          class="pdf-preview-document"
          :source="pdfSource"
          :annotation-layer="true"
          :text-layer="true"
          @loaded="handleLoaded"
          @progress="handleProgress"
          @rendered="handleRendered"
          @loading-failed="handleFailed"
          @rendering-failed="handleFailed"
        />
      </div>

      <div v-else class="pdf-preview-error" role="status">
        <h3>{{ title }}</h3>
        <p>
          {{
            errorMessage ||
            "当前 PDF 预览无法在页内渲染，请尝试新窗口打开或下载原文件。"
          }}
        </p>
      </div>

      <template #fallback>
        <div
          class="pdf-preview-loading pdf-preview-loading--fallback"
          role="status"
        >
          <span class="pdf-preview-loading__spinner" />
          <p>正在初始化 PDF 预览器...</p>
        </div>
      </template>
    </ClientOnly>
  </div>
</template>

<style scoped>
.pdf-preview-shell {
  min-height: 0;
}

.pdf-preview-stage,
.pdf-preview-loading,
.pdf-preview-error {
  border: 1px solid #e9e0d0;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 20px 48px rgba(34, 24, 12, 0.06);
}

.pdf-preview-stage {
  position: relative;
  min-height: 680px;
  max-height: 75vh;
  overflow: auto;
  padding: 20px;
}

.pdf-preview-document {
  width: 100%;
}

.pdf-preview-loading,
.pdf-preview-error {
  display: grid;
  place-items: center;
  gap: 12px;
  min-height: 320px;
  padding: 28px;
  text-align: center;
  color: #655f56;
}

.pdf-preview-loading--fallback {
  min-height: 220px;
}

.pdf-preview-loading__spinner {
  width: 28px;
  height: 28px;
  border: 3px solid rgba(49, 88, 255, 0.16);
  border-top-color: #3158ff;
  border-radius: 999px;
  animation: pdf-preview-spin 0.8s linear infinite;
}

.pdf-preview-error h3 {
  font-size: 1rem;
  font-weight: 700;
  color: #18181b;
}

.pdf-preview-error p {
  max-width: 42rem;
  line-height: 1.75;
}

:deep(.vue-pdf-embed > div) {
  margin-bottom: 18px;
}

:deep(.vue-pdf-embed canvas) {
  width: 100% !important;
  height: auto !important;
  border-radius: 18px;
  box-shadow: 0 10px 24px rgba(24, 24, 27, 0.08);
}

@keyframes pdf-preview-spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 767px) {
  .pdf-preview-stage {
    min-height: 520px;
    max-height: none;
    padding: 12px;
  }
}
</style>
