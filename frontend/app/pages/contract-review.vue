<script setup lang="ts">
import { storeToRefs } from "pinia";
import { useContractReviewStore } from "../../stores/contractReview";

const store = useContractReviewStore();
const {
  activeTab,
  detail,
  jobs,
  templates,
  isCreatingJob,
  isLoadingDetail,
  isLoadingJobs,
  isLoadingTemplates,
  isUploadingTemplate,
  deletingTemplateIds,
  deletingJobIds,
} = storeToRefs(store);

const acceptedFormats = ".pdf,.docx";
const reviewFile = ref<File | null>(null);
const templateFile = ref<File | null>(null);
const reviewName = ref("");
const selectedTemplateId = ref("");
const templateForm = reactive({
  name: "",
  description: "",
});

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
  if (severity === "high") return "error";
  if (severity === "medium") return "warning";
  return "neutral";
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

function onReviewFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  reviewFile.value = input.files?.[0] ?? null;
}

function onTemplateFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  templateFile.value = input.files?.[0] ?? null;
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
  if (!templateFile.value || !templateForm.name.trim()) return;
  await store.uploadTemplate({
    file: templateFile.value,
    name: templateForm.name,
    description: templateForm.description,
  });
  templateFile.value = null;
  templateForm.name = "";
  templateForm.description = "";
}

async function handleDeleteJob(jobId: string) {
  if (
    !window.confirm("移除后会删除该任务及其导出结果，确定继续吗？")
  ) {
    return;
  }
  await store.deleteJob(jobId);
}

onMounted(async () => {
  await Promise.all([store.fetchTemplates(), store.fetchJobs()]);
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
              :accept="acceptedFormats"
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
                placeholder="例如：供应商框架协议首轮审查"
              />
            </div>
            <div class="field">
              <label>选择清单</label>
              <USelect
                v-model="selectedTemplateId"
                :items="
                  templates.map((item) => ({
                    label: item.name,
                    value: item.id,
                  }))
                "
                value-key="value"
                placeholder="请选择清单"
              />
            </div>
          </div>

          <div class="actions">
            <UButton
              color="neutral"
              variant="ghost"
              @click="activeTab = 'template-upload'"
              >管理清单</UButton
            >
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
                >导出 DOCX</UButton
              >
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
            </div>
            <UBadge
              :color="getStatusColor(detail.job.status) as any"
              variant="subtle"
            >
              {{ getStatusLabel(detail.job.status) }}
            </UBadge>
          </div>

          <div class="stats">
            <div class="stat">
              <span>总检查项</span><strong>{{ detail.checklist.total }}</strong>
            </div>
            <div class="stat">
              <span>预警</span><strong>{{ detail.checklist.warnings }}</strong>
            </div>
            <div class="stat">
              <span>缺失/失败</span
              ><strong>{{
                detail.checklist.failed + detail.checklist.missing
              }}</strong>
            </div>
          </div>

          <div class="dual">
            <div class="panel">
              <div class="card-head">
                <h3>风险与改写建议</h3>
                <span>{{ detail.findings.length }} 项</span>
              </div>
              <div v-if="detail.findings.length" class="stack">
                <article
                  v-for="finding in detail.findings"
                  :key="finding.id"
                  class="list-card"
                >
                  <div class="card-head">
                    <div>
                      <p class="title">{{ finding.title }}</p>
                      <p class="subtle">
                        {{ finding.clause_path || "未定位条款" }}
                      </p>
                    </div>
                    <UBadge
                      :color="
                        getFindingColor(finding.status, finding.severity) as any
                      "
                      variant="subtle"
                      size="sm"
                    >
                      {{ finding.severity }} / {{ finding.status }}
                    </UBadge>
                  </div>
                  <p class="subtle">{{ finding.issue }}</p>
                  <p v-if="finding.evidence" class="evidence">
                    {{ finding.evidence }}
                  </p>
                  <div v-if="finding.rewrite_suggestion" class="rewrite">
                    {{ finding.rewrite_suggestion }}
                  </div>
                </article>
              </div>
              <div v-else class="empty">任务尚未生成风险项。</div>
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
                      >第 {{ clause.page_start }} -
                      {{ clause.page_end }} 页</span
                    >
                  </div>
                  <p class="title">{{ clause.title }}</p>
                  <p class="subtle prewrap">{{ clause.content }}</p>
                </article>
              </div>
              <div v-else class="empty">还没有可展示的条款内容。</div>
            </div>
          </div>

          <div class="future">
            <div class="list-card">多版本对比：即将支持</div>
            <div class="list-card">角色化审查：即将支持</div>
            <div class="list-card">法条与案例联动：即将支持</div>
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

    <section v-else-if="activeTab === 'template-upload'">
      <UCard class="card">
        <template #header>
          <div class="card-head">
            <div>
              <p class="eyebrow">Library</p>
              <h2>上传审查清单</h2>
            </div>
          </div>
        </template>

        <div class="stack">
          <label class="dropzone">
            <input
              type="file"
              :accept="acceptedFormats"
              class="hidden"
              @change="onTemplateFileChange"
            />
            <UIcon
              name="i-lucide-library-big"
              class="h-10 w-10 text-[#3158ff]"
            />
            <div>
              <p class="title">上传审查清单文件</p>
              <p class="subtle">仅需填写清单名称，可选补充清单说明。</p>
            </div>
          </label>

          <div v-if="templateFile" class="pill">
            <div>
              <p class="title">{{ templateFile.name }}</p>
              <p class="subtle">{{ formatFileSize(templateFile.size) }}</p>
            </div>
            <UButton
              icon="i-lucide-x"
              color="neutral"
              variant="ghost"
              size="xs"
              @click="templateFile = null"
            />
          </div>

          <div class="fields">
            <div class="field">
              <label>清单名称</label>
              <UInput
                v-model="templateForm.name"
                placeholder="请输入清单名称"
              />
            </div>
          </div>

          <div class="field">
            <label>清单说明（可选）</label>
            <UTextarea
              v-model="templateForm.description"
              :rows="4"
              placeholder="可补充清单用途、适用场景等"
            />
          </div>

          <div class="actions">
            <UButton
              color="neutral"
              variant="ghost"
              :loading="isLoadingTemplates"
              @click="store.fetchTemplates()"
              >刷新列表</UButton
            >
            <UButton
              color="primary"
              :disabled="!templateFile || !templateForm.name.trim()"
              :loading="isUploadingTemplate"
              @click="submitTemplate"
            >
              上传审查清单
            </UButton>
          </div>
        </div>
      </UCard>
    </section>

    <section v-else-if="activeTab === 'template-list'">
      <UCard class="card">
        <template #header>
          <div class="card-head">
            <div>
              <p class="eyebrow">Catalog</p>
              <h2>审查清单列表</h2>
            </div>
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
            <p class="subtle">
              {{ item.description || "当前清单已绑定默认审查配置。" }}
            </p>
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
.tabs {
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
.future,
.dual,
.grid-layout,
.result-layout {
  display: grid;
  gap: 14px;
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
.overview {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.stack {
  display: grid;
  gap: 14px;
}
.dropzone,
.pill,
.list-card,
.panel {
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
.panel {
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
.field label {
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
.evidence,
.rewrite {
  margin-top: 10px;
  border-radius: 18px;
  padding: 12px 14px;
}
.evidence {
  background: #fbf6ed;
}
.rewrite {
  background: rgba(49, 88, 255, 0.06);
  color: #2f4fb9;
  line-height: 1.7;
}
.prewrap {
  white-space: pre-wrap;
  max-height: 160px;
  overflow: auto;
}
@media (min-width: 960px) {
  .hero {
    grid-template-columns: minmax(0, 1.5fr) 320px;
    align-items: start;
  }
  .stats,
  .future {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .fields {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .grid-layout {
    grid-template-columns: minmax(0, 1.1fr) minmax(320px, 0.9fr);
  }
  .result-layout {
    grid-template-columns: minmax(0, 1.3fr) 320px;
  }
  .dual {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
