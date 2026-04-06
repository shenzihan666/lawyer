<script setup lang="ts">
import { storeToRefs } from "pinia";
import { useContractReviewStore } from "../../stores/contractReview";

const store = useContractReviewStore();
const {
  activeTab,
  detail,
  jobs,
  settings,
  templates,
  isCreatingJob,
  isLoadingDetail,
  isLoadingJobs,
  isLoadingSettings,
  isLoadingTemplates,
  isUploadingTemplate,
  isSavingSettings,
  deletingTemplateIds,
  deletingJobIds,
} = storeToRefs(store);

const reviewAcceptedFormats = ".pdf,.docx";
const templateAcceptedFormats = ".xlsx";
const reviewFile = ref<File | null>(null);
const templateFiles = ref<File[]>([]);
const reviewName = ref("");
const globalRuleDraft = ref("");
const selectedTemplateId = ref("");
const selectedUploadRows = ref<Record<string, boolean>>({});

const tabs = [
  { key: "launch", label: "发起审查", icon: "i-lucide-rocket" },
  { key: "results", label: "审查结果", icon: "i-lucide-file-search" },
  {
    key: "template-upload",
    label: "上传审查清单",
    icon: "i-lucide-library-big",
  },
  { key: "template-list", label: "审查清单列表", icon: "i-lucide-list" },
] as const;

const selectedJob = computed(
  () =>
    detail.value?.job ??
    jobs.value.find((item) => item.id === store.activeJobId) ??
    null,
);

const stagedTemplateRows = computed(() =>
  templateFiles.value.map((file) => ({
    key: `${file.name}-${file.size}-${file.lastModified}`,
    file,
  })),
);
const selectedUploadKeys = computed(() =>
  stagedTemplateRows.value
    .map((item) => item.key)
    .filter((key) => Boolean(selectedUploadRows.value[key])),
);
const selectedUploadFiles = computed(() =>
  stagedTemplateRows.value
    .filter((item) => Boolean(selectedUploadRows.value[item.key]))
    .map((item) => item.file),
);
const hasUploadSelection = computed(() => selectedUploadKeys.value.length > 0);
const allUploadSelected = computed(
  () =>
    stagedTemplateRows.value.length > 0 &&
    selectedUploadKeys.value.length === stagedTemplateRows.value.length,
);

watch(
  () => settings.value.global_rule_prompt,
  (value) => {
    globalRuleDraft.value = value;
  },
  { immediate: true },
);

function formatDate(value: string | null) {
  if (!value) return "未完成";
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatFileSize(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function getStatusLabel(status: string) {
  return (
    {
      queued: "排队中",
      running: "审查中",
      completed: "已完成",
      failed: "失败",
    }[status] || status
  );
}

function getStatusColor(status: string) {
  return (
    {
      completed: "success",
      failed: "error",
      queued: "warning",
      running: "warning",
    }[status] || "neutral"
  );
}

function getFindingColor(status: string, severity: string) {
  if (status === "pass") return "success";
  if (status === "fail") return "error";
  if (status === "warn" || severity === "medium") return "warning";
  return "neutral";
}

function getFindingStatusLabel(status: string) {
  return (
    {
      pass: "通过",
      warn: "预警",
      fail: "失败",
      missing: "缺失",
    }[status] || status
  );
}

function isJobRemovable(status: string) {
  return !["queued", "running"].includes(status);
}

function getRemoveJobHint(status: string) {
  return isJobRemovable(status) ? "移除任务" : "审查进行中，暂不可移除";
}

function isJobProcessing(status: string) {
  return ["queued", "running"].includes(status);
}

function getTemplateChecklistCount(template: { config_json: Record<string, unknown> }) {
  const checklist = template.config_json.checklist;
  return Array.isArray(checklist) ? checklist.length : 0;
}

function onReviewFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  reviewFile.value = input.files?.[0] ?? null;
}

function onTemplateFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  const files = [...(input.files ?? [])];
  mergeTemplateFiles(files);
  input.value = "";
}

function onTemplateDrop(event: DragEvent) {
  const files = [...(event.dataTransfer?.files ?? [])];
  mergeTemplateFiles(files);
}

function mergeTemplateFiles(files: File[]) {
  const next = new Map(
    templateFiles.value.map((file) => [
      `${file.name}-${file.size}-${file.lastModified}`,
      file,
    ]),
  );
  for (const file of files) {
    next.set(`${file.name}-${file.size}-${file.lastModified}`, file);
  }
  templateFiles.value = [...next.values()];
}

function removeTemplateFile(target: File) {
  templateFiles.value = templateFiles.value.filter(
    (file) =>
      file.name !== target.name ||
      file.size !== target.size ||
      file.lastModified !== target.lastModified,
  );
}

function clearTemplateDraft() {
  templateFiles.value = [];
  selectedUploadRows.value = {};
}

async function submitReview() {
  if (!reviewFile.value || !selectedTemplateId.value) return;
  await store.createReviewJob({
    file: reviewFile.value,
    templateId: selectedTemplateId.value,
    reviewName: reviewName.value,
  });
}

async function submitTemplate() {
  if (!selectedUploadFiles.value.length) return;
  const keySet = new Set(selectedUploadKeys.value);
  await store.uploadTemplates(selectedUploadFiles.value);
  templateFiles.value = stagedTemplateRows.value
    .filter((item) => !keySet.has(item.key))
    .map((item) => item.file);
  selectedUploadRows.value = {};
  const firstTemplate = templates.value[0];
  if (firstTemplate && !selectedTemplateId.value) {
    selectedTemplateId.value = firstTemplate.id;
  }
}

async function submitGlobalRule() {
  await store.saveSettings(globalRuleDraft.value);
}

function deleteSelectedUploadFiles() {
  if (!selectedUploadKeys.value.length) return;
  const keySet = new Set(selectedUploadKeys.value);
  templateFiles.value = stagedTemplateRows.value
    .filter((item) => !keySet.has(item.key))
    .map((item) => item.file);
  selectedUploadRows.value = {};
}

function toggleUploadSelection(key: string, checked: boolean) {
  if (checked) {
    selectedUploadRows.value = {
      ...selectedUploadRows.value,
      [key]: true,
    };
    return;
  }

  const next = { ...selectedUploadRows.value };
  delete next[key];
  selectedUploadRows.value = next;
}

function selectAllUploadFiles() {
  const next: Record<string, boolean> = {};
  for (const item of stagedTemplateRows.value) {
    next[item.key] = true;
  }
  selectedUploadRows.value = next;
}

function clearSelectedUploadFiles() {
  selectedUploadRows.value = {};
}

async function handleDeleteJob(jobId: string) {
  if (!window.confirm("移除后会删除该任务及其导出结果，确定继续吗？")) {
    return;
  }
  await store.deleteJob(jobId);
}

onMounted(async () => {
  await Promise.all([
    store.fetchSettings(),
    store.fetchTemplates(),
    store.fetchJobs(),
  ]);
  const firstTemplate = templates.value[0];
  if (firstTemplate && !selectedTemplateId.value) {
    selectedTemplateId.value = firstTemplate.id;
  }
  const firstJob = jobs.value[0];
  if (firstJob) {
    await store.fetchJobDetail(firstJob.id, { quiet: true });
  }
});

onBeforeUnmount(() => {
  store.stopPolling();
});
</script>

<template>
  <div class="page-shell px-4 py-6 md:px-8 md:py-8">
    <section class="hero">
      <div class="hero-copy">
        <p class="eyebrow">Contract Review</p>
        <h1>合同审查</h1>
        <p class="copy">
          上传 Excel 审查清单后，系统会将清单项与全局规则一起注入 AI，
          对待审合同生成逐项、可追溯的结构化审查结果。
        </p>
      </div>
      <div class="stats hero-stats">
        <div class="stat">
          <span>清单库</span>
          <strong>{{ templates.length }} 个清单</strong>
        </div>
        <div class="stat">
          <span>任务数</span>
          <strong>{{ jobs.length }} 个任务</strong>
        </div>
        <div class="stat">
          <span>高关注</span>
          <strong>{{ detail?.checklist.high_risk ?? 0 }} 项</strong>
        </div>
      </div>
    </section>

    <div class="tabs" role="tablist" aria-label="合同审查导航">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        type="button"
        class="tab"
        :class="{ 'tab--active': activeTab === tab.key }"
        @click="activeTab = tab.key"
      >
        <UIcon :name="tab.icon" class="h-4 w-4" />
        <span>{{ tab.label }}</span>
      </button>
    </div>

    <section v-if="activeTab === 'launch'" class="stack">
      <UCard class="card">
        <template #header>
          <div class="card-head">
            <div>
              <p class="eyebrow">Launch</p>
              <h2>发起新审查</h2>
            </div>
          </div>
        </template>

        <div class="stack">
          <label class="dropzone">
            <input
              type="file"
              :accept="reviewAcceptedFormats"
              class="hidden"
              @change="onReviewFileChange"
            />
            <UIcon name="i-lucide-file-up" class="h-10 w-10 text-[#3158ff]" />
            <div>
              <p class="title">上传待审合同</p>
              <p class="subtle">
                支持 PDF / Word，建议上传正式版或对方最新修订版。
              </p>
            </div>
          </label>

          <div v-if="reviewFile" class="pill">
            <div>
              <p class="title">{{ reviewFile.name }}</p>
              <p class="subtle">{{ formatFileSize(reviewFile.size) }}</p>
            </div>
            <UButton
              icon="i-lucide-x"
              color="neutral"
              variant="ghost"
              size="xs"
              @click="reviewFile = null"
            />
          </div>

          <div class="fields">
            <div class="field">
              <label>审查名称</label>
              <UInput
                v-model="reviewName"
                placeholder="例如：股权转让协议首轮审查"
              />
            </div>
            <div class="field">
              <label>选择清单</label>
              <USelect
                v-model="selectedTemplateId"
                :items="
                  templates.map((item) => ({
                    label: `${item.name}（${getTemplateChecklistCount(item)} 项）`,
                    value: item.id,
                  }))
                "
                value-key="value"
                placeholder="请选择清单"
              />
            </div>
          </div>

          <div class="rule-banner">
            <div>
              <p class="title">当前全局规则</p>
              <p class="subtle">
                {{
                  settings.global_rule_prompt ||
                  "尚未设置，全局规则为空时只使用所选清单内容。"
                }}
              </p>
            </div>
            <UButton color="neutral" variant="ghost" @click="activeTab = 'template-list'">
              配置全局规则
            </UButton>
          </div>

          <div class="actions">
            <UButton
              color="neutral"
              variant="ghost"
              @click="activeTab = 'template-upload'"
            >
              管理清单
            </UButton>
            <UButton
              color="primary"
              :disabled="!reviewFile || !selectedTemplateId"
              :loading="isCreatingJob"
              @click="submitReview"
            >
              发起合同审查
            </UButton>
          </div>
        </div>
      </UCard>
    </section>

    <section v-else-if="activeTab === 'results'" class="result-layout">
      <UCard class="card">
        <template #header>
          <div class="card-head">
            <div>
              <p class="eyebrow">Result</p>
              <h2>审查结果</h2>
            </div>
            <div class="actions">
              <UButton
                icon="i-lucide-refresh-cw"
                color="neutral"
                variant="ghost"
                :disabled="!selectedJob"
                :loading="isLoadingDetail"
                @click="selectedJob && store.fetchJobDetail(selectedJob.id)"
              />
              <UButton
                color="primary"
                :disabled="!detail?.export.available"
                @click="store.downloadExport()"
              >
                导出 DOCX
              </UButton>
            </div>
          </div>
        </template>

        <div v-if="!detail" class="empty">
          选择一个审查任务后，这里会展示结构化结果。
        </div>
        <div v-else class="stack">
          <div class="overview">
            <div>
              <p class="title">{{ detail.job.review_name }}</p>
              <p class="subtle">
                {{ detail.job.original_filename }} ·
                {{ detail.template?.name || "未绑定清单" }}
              </p>
              <p v-if="detail.job.failure_reason" class="error-text">
                {{ detail.job.failure_reason }}
              </p>
            </div>
            <div class="status-stack">
              <UBadge
                :color="getStatusColor(detail.job.status) as any"
                variant="subtle"
              >
                {{ getStatusLabel(detail.job.status) }}
              </UBadge>
              <span class="subtle">{{ formatDate(detail.job.completed_at) }}</span>
            </div>
          </div>

          <div class="stats stats--dense">
            <div class="stat">
              <span>总检查项</span><strong>{{ detail.checklist.total }}</strong>
            </div>
            <div class="stat">
              <span>通过</span><strong>{{ detail.checklist.passed }}</strong>
            </div>
            <div class="stat">
              <span>预警</span><strong>{{ detail.checklist.warnings }}</strong>
            </div>
            <div class="stat">
              <span>失败</span><strong>{{ detail.checklist.failed }}</strong>
            </div>
            <div class="stat">
              <span>缺失</span><strong>{{ detail.checklist.missing }}</strong>
            </div>
            <div class="stat">
              <span>高风险</span><strong>{{ detail.checklist.high_risk }}</strong>
            </div>
          </div>

          <div class="panel">
            <div class="card-head">
              <h3>逐项审查结果</h3>
              <span>{{ detail.findings.length }} 项</span>
            </div>
            <div v-if="detail.findings.length" class="stack">
              <article
                v-for="finding in detail.findings"
                :key="finding.id"
                class="list-card"
              >
                <div class="card-head">
                  <div class="stack-tight">
                    <div class="badge-row">
                      <UBadge color="neutral" variant="subtle" size="xs">
                        原始风险：{{ finding.checklist_item.risk_level || "未标注" }}
                      </UBadge>
                      <UBadge
                        :color="getFindingColor(finding.status, finding.severity) as any"
                        variant="subtle"
                        size="xs"
                      >
                        {{ getFindingStatusLabel(finding.status) }} / {{ finding.severity }}
                      </UBadge>
                    </div>
                    <p class="title">{{ finding.checklist_item.title || finding.title }}</p>
                    <p class="subtle">{{ finding.checklist_item.description }}</p>
                  </div>
                </div>

                <div class="finding-section">
                  <span class="section-label">问题说明</span>
                  <p class="subtle">{{ finding.issue }}</p>
                </div>

                <div
                  v-if="finding.evidence_items.length"
                  class="finding-section evidence-list"
                >
                  <span class="section-label">证据定位</span>
                  <article
                    v-for="(evidence, index) in finding.evidence_items"
                    :key="`${finding.id}-${index}`"
                    class="evidence-card"
                  >
                    <div class="card-head">
                      <strong>{{ evidence.clause_path || "未定位条款" }}</strong>
                      <span class="subtle">
                        {{
                          evidence.page_start && evidence.page_end
                            ? `第 ${evidence.page_start}-${evidence.page_end} 页`
                            : "页码未知"
                        }}
                      </span>
                    </div>
                    <p class="title">{{ evidence.clause_title }}</p>
                    <p class="subtle">{{ evidence.excerpt }}</p>
                  </article>
                </div>

                <div v-if="finding.rewrite_suggestion" class="rewrite">
                  <span class="section-label">修改建议</span>
                  <p>{{ finding.rewrite_suggestion }}</p>
                </div>

                <div
                  v-if="
                    finding.checklist_item.related_clauses?.length ||
                    finding.checklist_item.related_knowledge_points?.length
                  "
                  class="meta-grid"
                >
                  <div v-if="finding.checklist_item.related_clauses?.length" class="meta-box">
                    <span class="section-label">清单相关条款</span>
                    <p class="subtle">
                      {{ finding.checklist_item.related_clauses.join("、") }}
                    </p>
                  </div>
                  <div
                    v-if="finding.checklist_item.related_knowledge_points?.length"
                    class="meta-box"
                  >
                    <span class="section-label">清单相关知识点</span>
                    <p class="subtle">
                      {{
                        finding.checklist_item.related_knowledge_points.join("；")
                      }}
                    </p>
                  </div>
                </div>
              </article>
            </div>
            <div v-else class="empty">任务尚未生成逐项结果。</div>
          </div>

          <div class="panel">
            <div class="card-head">
              <h3>条款预览</h3>
              <span>{{ detail.clauses.length }} 段</span>
            </div>
            <div v-if="detail.clauses.length" class="stack">
              <article
                v-for="clause in detail.clauses"
                :key="clause.id"
                class="list-card"
              >
                <div class="card-head">
                  <strong>{{ clause.clause_path }}</strong>
                  <span class="subtle"
                    >第 {{ clause.page_start }} - {{ clause.page_end }} 页</span
                  >
                </div>
                <p class="title">{{ clause.title }}</p>
                <p class="subtle prewrap">{{ clause.content }}</p>
              </article>
            </div>
            <div v-else class="empty">还没有可展示的条款内容。</div>
          </div>
        </div>
      </UCard>

      <UCard class="card">
        <template #header>
          <div class="card-head">
            <div>
              <p class="eyebrow">All Tasks</p>
              <h2>所有任务</h2>
            </div>
            <UButton
              icon="i-lucide-refresh-cw"
              color="neutral"
              variant="ghost"
              :loading="isLoadingJobs"
              @click="store.fetchJobs()"
            />
          </div>
        </template>
        <div v-if="!jobs.length" class="empty">当前没有可查看的审查任务。</div>
        <div v-else class="stack">
          <article
            v-for="job in jobs"
            :key="job.id"
            class="list-card list-card--task"
            :class="{ 'list-card--active': selectedJob?.id === job.id }"
          >
            <button
              type="button"
              class="list-card__button"
              @click="store.selectJob(job.id)"
            >
              <div class="card-head">
                <div>
                  <p class="title">{{ job.review_name }}</p>
                  <p v-if="isJobProcessing(job.status)" class="subtle">
                    正在处理中
                  </p>
                  <p v-else class="subtle">{{ formatDate(job.completed_at) }}</p>
                </div>
                <UBadge
                  :color="getStatusColor(job.status) as any"
                  variant="subtle"
                  size="xs"
                >
                  {{ getStatusLabel(job.status) }}
                </UBadge>
              </div>
              <p class="subtle">{{ job.original_filename }}</p>
            </button>
            <UButton
              icon="i-lucide-trash-2"
              color="error"
              variant="ghost"
              size="xs"
              class="list-card__action"
              :title="getRemoveJobHint(job.status)"
              :disabled="!isJobRemovable(job.status)"
              :loading="deletingJobIds.includes(job.id)"
              @click.stop="handleDeleteJob(job.id)"
            />
          </article>
        </div>
      </UCard>
    </section>

    <section
      v-else-if="activeTab === 'template-upload'"
      class="grid gap-6 xl:grid-cols-[360px_minmax(0,1fr)]"
    >
      <UCard
        class="rounded-[28px] ring-1 ring-[#ebe5da] shadow-[0_20px_60px_rgba(34,24,12,0.05)]"
      >
        <template #header>
          <div class="flex items-center justify-between gap-3">
            <div>
              <h2 class="text-base font-semibold text-zinc-900">上传审查清单</h2>
              <p class="mt-1 text-sm text-zinc-500">
                仅支持 Excel 清单（.xlsx），可选择多个文件批量入库。
              </p>
            </div>
            <UBadge color="neutral" variant="subtle" size="sm">XLSX</UBadge>
          </div>
        </template>

        <div class="space-y-4">
          <label
            class="block rounded-[24px] border-2 border-dashed border-zinc-200 px-6 py-12 text-center transition-colors hover:border-zinc-400 hover:bg-zinc-50/50"
            @dragover.prevent
            @drop.prevent="onTemplateDrop"
          >
            <input
              type="file"
              :accept="templateAcceptedFormats"
              multiple
              class="hidden"
              @change="onTemplateFileChange"
            />
            <UIcon
              name="i-lucide-upload-cloud"
              class="mx-auto mb-4 h-10 w-10 text-zinc-400"
            />
            <p class="text-base font-medium text-zinc-900">
              点击或拖拽 Excel 清单到此处
            </p>
            <p class="mt-2 text-sm text-zinc-500">支持 `.xlsx` 文件</p>
          </label>

          <div class="flex items-center justify-end gap-3 pt-2">
            <UBadge color="neutral" variant="subtle" size="sm">
              待上传 {{ templateFiles.length }} 个
            </UBadge>
            <UButton
              color="neutral"
              variant="ghost"
              :disabled="isUploadingTemplate"
              @click="clearTemplateDraft"
            >
              清空
            </UButton>
          </div>
        </div>
      </UCard>

      <UCard
        class="rounded-[28px] ring-1 ring-[#ebe5da] shadow-[0_20px_60px_rgba(34,24,12,0.05)]"
      >
        <template #header>
          <div class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 class="text-base font-semibold text-zinc-900">上传管理</h2>
              <p class="mt-1 text-sm text-zinc-500">
                勾选后再上传或删除，系统会自动解析 Excel 中的风险块。
              </p>
            </div>
            <div class="flex flex-wrap items-center gap-2">
              <UButton
                color="neutral"
                variant="ghost"
                size="sm"
                :disabled="!stagedTemplateRows.length || allUploadSelected"
                @click="selectAllUploadFiles"
              >
                全选
              </UButton>
              <UButton
                color="neutral"
                variant="ghost"
                size="sm"
                :disabled="!hasUploadSelection"
                @click="clearSelectedUploadFiles"
              >
                取消全选
              </UButton>
              <UButton
                color="primary"
                size="sm"
                :disabled="!hasUploadSelection"
                :loading="isUploadingTemplate"
                @click="submitTemplate"
              >
                上传
              </UButton>
              <UButton
                color="error"
                variant="soft"
                size="sm"
                :disabled="!hasUploadSelection"
                @click="deleteSelectedUploadFiles"
              >
                删除
              </UButton>
            </div>
          </div>
        </template>

        <div
          v-if="!stagedTemplateRows.length"
          class="rounded-[24px] border border-dashed border-zinc-200 bg-zinc-50/80 px-6 py-12 text-center"
        >
          <UIcon
            name="i-lucide-library-big"
            class="mx-auto mb-3 h-10 w-10 text-zinc-300"
          />
          <p class="text-base font-medium text-zinc-900">暂无待上传文件</p>
          <p class="mt-2 text-sm text-zinc-500">
            先在左侧拖拽或选择文件，这里会显示待上传列表。
          </p>
        </div>

        <div v-else class="space-y-3">
          <article
            v-for="item in stagedTemplateRows"
            :key="item.key"
            class="rounded-2xl border border-zinc-100 bg-zinc-50 px-4 py-3"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="flex min-w-0 items-start gap-3">
                <UCheckbox
                  :model-value="selectedUploadRows[item.key] === true"
                  @update:model-value="
                    ($event) => toggleUploadSelection(item.key, !!$event)
                  "
                />
                <div class="min-w-0">
                  <p class="truncate text-sm font-semibold text-zinc-900">
                    {{ item.file.name }}
                  </p>
                  <p class="mt-1 text-xs text-zinc-500">
                    {{ formatFileSize(item.file.size) }}
                  </p>
                </div>
              </div>
              <UButton
                icon="i-lucide-trash-2"
                color="error"
                variant="ghost"
                size="xs"
                @click="removeTemplateFile(item.file)"
              />
            </div>
          </article>
        </div>
      </UCard>
    </section>

    <section v-else-if="activeTab === 'template-list'" class="stack">
      <UCard class="card">
        <template #header>
          <div class="card-head">
            <div>
              <p class="eyebrow">Global Rule</p>
              <h2>全局规则</h2>
            </div>
            <UBadge color="neutral" variant="subtle" size="sm">
              {{ isLoadingSettings ? "加载中" : "模块级共享" }}
            </UBadge>
          </div>
        </template>

        <div class="stack">
          <p class="subtle">
            这里的规则会对所有合同审查任务生效，并和所选清单一起注入 AI 提示词。
          </p>
          <textarea
            v-model="globalRuleDraft"
            class="rule-textarea"
            placeholder="例如：对于 fail / warn 项，优先指出风险后果，并给出可落地的改写建议。"
          />
          <div class="actions">
            <span class="subtle">当前字数：{{ globalRuleDraft.length }}</span>
            <UButton
              color="primary"
              :loading="isSavingSettings"
              @click="submitGlobalRule"
            >
              保存全局规则
            </UButton>
          </div>
        </div>
      </UCard>

      <UCard class="card">
        <template #header>
          <div class="card-head">
            <div>
              <p class="eyebrow">Catalog</p>
              <h2>审查清单列表</h2>
            </div>
            <UButton
              icon="i-lucide-refresh-cw"
              color="neutral"
              variant="ghost"
              :loading="isLoadingTemplates"
              @click="store.fetchTemplates()"
            />
          </div>
        </template>

        <div v-if="!templates.length" class="empty">
          还没有审查清单，可以先上传团队清单。
        </div>
        <div v-else class="stack">
          <article v-for="item in templates" :key="item.id" class="list-card">
            <div class="card-head">
              <div>
                <p class="title">{{ item.name }}</p>
                <p class="subtle">
                  {{ item.category }} · {{ item.original_filename }}
                </p>
              </div>
              <div class="actions">
                <UBadge
                  :color="item.source_type === 'seed' ? 'neutral' : 'primary'"
                  variant="subtle"
                  size="xs"
                >
                  {{ item.source_type === "seed" ? "种子清单" : "手动上传" }}
                </UBadge>
                <UButton
                  icon="i-lucide-trash-2"
                  color="error"
                  variant="ghost"
                  size="xs"
                  :loading="deletingTemplateIds.includes(item.id)"
                  @click="store.deleteTemplate(item.id)"
                />
              </div>
            </div>
            <div class="meta-grid">
              <div class="meta-box">
                <span class="section-label">说明</span>
                <p class="subtle">
                  {{ item.description || "当前清单已解析为 Excel 审查模板。" }}
                </p>
              </div>
              <div class="meta-box">
                <span class="section-label">检查项</span>
                <p class="subtle">{{ getTemplateChecklistCount(item) }} 项</p>
              </div>
            </div>
          </article>
        </div>
      </UCard>
    </section>
  </div>
</template>

<style scoped>
.page-shell {
  min-height: 100vh;
  background:
    radial-gradient(
      circle at top left,
      rgba(189, 214, 255, 0.68),
      transparent 28%
    ),
    radial-gradient(
      circle at bottom right,
      rgba(247, 228, 196, 0.8),
      transparent 32%
    ),
    linear-gradient(180deg, #f8f5ee, #fbfaf7);
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.hero,
.card,
.list-card,
.dropzone,
.pill,
.panel,
.stat,
.tabs,
.rule-banner {
  border: 1px solid #e8dfd0;
  background: rgba(255, 255, 255, 0.84);
  box-shadow: 0 20px 48px rgba(34, 24, 12, 0.06);
}
.hero,
.card {
  border-radius: 30px;
}
.hero {
  display: grid;
  gap: 20px;
  padding: 16px 24px 18px;
  background: linear-gradient(
    135deg,
    rgba(255, 255, 255, 0.96),
    rgba(250, 246, 238, 0.94)
  );
}
.hero-copy {
  display: grid;
  align-content: start;
}
.hero-stats {
  align-self: start;
}
.eyebrow {
  font-size: 11px;
  letter-spacing: 0.24em;
  text-transform: uppercase;
  color: #8a8579;
}
h1 {
  margin-top: 10px;
  font-size: clamp(2rem, 3vw, 3rem);
  line-height: 1;
  letter-spacing: -0.05em;
  color: #18181b;
}
h2,
h3,
.title,
strong {
  color: #18181b;
}
.copy,
.subtle {
  line-height: 1.8;
  color: #665f55;
}
.copy {
  margin-top: 12px;
  max-width: 820px;
}
.stats,
.fields,
.meta-grid,
.result-layout {
  display: grid;
  gap: 14px;
}
.stats--dense {
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
}
.stat {
  border-radius: 22px;
  padding: 16px;
}
.stat span {
  display: block;
  font-size: 12px;
  color: #8a8579;
}
.stat strong {
  display: block;
  margin-top: 10px;
  font-size: 1.1rem;
}
.tabs {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  align-self: start;
  gap: 8px;
  width: fit-content;
  max-width: 100%;
  padding: 8px;
  border-radius: 26px;
  background: rgba(255, 255, 255, 0.78);
}
.tab {
  appearance: none;
  border: 1px solid transparent;
  border-radius: 18px;
  height: 56px;
  padding: 12px 18px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  flex: 0 0 auto;
  width: auto;
  min-width: 132px;
  background: transparent;
  color: #5a5a55;
  font-weight: 600;
  white-space: nowrap;
  transition: 0.18s;
}
.tab--active {
  border-color: #3158ff;
  color: #3158ff;
  background: rgba(243, 247, 255, 0.92);
  box-shadow: none;
}
.card {
  padding: 0;
}
.card-head,
.actions,
.overview,
.badge-row,
.status-stack {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.status-stack {
  flex-direction: column;
  align-items: flex-end;
}
.stack {
  display: grid;
  gap: 14px;
}
.stack-tight {
  display: grid;
  gap: 8px;
}
.dropzone,
.pill,
.list-card,
.panel,
.rule-banner {
  border-radius: 24px;
  padding: 16px;
}
.dropzone {
  display: flex;
  align-items: center;
  gap: 16px;
  background: rgba(255, 250, 243, 0.9);
  cursor: pointer;
}
.pill,
.list-card,
.panel,
.rule-banner {
  background: rgba(255, 255, 255, 0.88);
}
.list-card {
  transition: 0.18s;
  text-align: left;
}
.list-card--task {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 12px 12px 16px;
}
.list-card__button {
  appearance: none;
  flex: 1;
  min-width: 0;
  display: grid;
  gap: 10px;
  border: 0;
  padding: 0;
  background: transparent;
  text-align: left;
  cursor: pointer;
}
.list-card__action {
  flex-shrink: 0;
  margin-top: 2px;
}
.list-card--active {
  border-color: #3158ff;
  background: linear-gradient(180deg, #fbfcff, #fff);
}
.field {
  display: grid;
  gap: 8px;
}
.field label,
.section-label {
  font-size: 0.84rem;
  font-weight: 600;
  color: #433f39;
}
.empty {
  border: 1px dashed #ddd2c0;
  border-radius: 24px;
  padding: 20px;
  color: #6b655b;
  background: rgba(255, 250, 244, 0.75);
  line-height: 1.8;
}
.finding-section {
  display: grid;
  gap: 8px;
}
.evidence-list {
  gap: 10px;
}
.evidence-card,
.meta-box {
  border-radius: 18px;
  padding: 12px 14px;
  background: #fbf6ed;
}
.rewrite {
  margin-top: 4px;
  border-radius: 18px;
  padding: 12px 14px;
  background: rgba(49, 88, 255, 0.06);
  color: #2f4fb9;
  line-height: 1.7;
}
.prewrap {
  white-space: pre-wrap;
  max-height: 160px;
  overflow: auto;
}
.rule-textarea {
  min-height: 160px;
  width: 100%;
  resize: vertical;
  border: 1px solid #d9cfbd;
  border-radius: 22px;
  padding: 16px;
  background: rgba(255, 252, 247, 0.86);
  color: #433f39;
  outline: none;
}
.rule-textarea:focus {
  border-color: #3158ff;
  box-shadow: 0 0 0 3px rgba(49, 88, 255, 0.12);
}
.error-text {
  color: #bb3d3d;
  line-height: 1.7;
}
@media (min-width: 960px) {
  .hero {
    grid-template-columns: minmax(0, 1.5fr) 320px;
    align-items: start;
  }
  .stats {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .fields,
  .meta-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .result-layout {
    grid-template-columns: minmax(0, 1.3fr) 320px;
  }
}
</style>
