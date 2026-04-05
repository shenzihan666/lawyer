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
} = storeToRefs(store);

const acceptedFormats = ".pdf,.doc,.docx";
const reviewFile = ref<File | null>(null);
const templateFile = ref<File | null>(null);
const reviewName = ref("");
const selectedTemplateId = ref("");
const templateForm = reactive({
  name: "",
  category: "通用合同",
  contractType: "general",
  description: "",
  configProfile: "general",
});

const tabs = [
  { key: "launch", label: "发起审查", icon: "i-lucide-rocket" },
  { key: "results", label: "审查结果", icon: "i-lucide-file-search" },
  { key: "templates", label: "模板库", icon: "i-lucide-library" },
] as const;

const profiles = [
  { label: "通用合同", value: "general" },
  { label: "劳动合同", value: "employment" },
  { label: "租赁合同", value: "lease" },
  { label: "保密协议", value: "nda" },
  { label: "买卖合同", value: "sales" },
];

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
    category: templateForm.category,
    contractType: templateForm.contractType,
    description: templateForm.description,
    configProfile: templateForm.configProfile,
  });
  templateFile.value = null;
  templateForm.name = "";
  templateForm.description = "";
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
      <div>
        <p class="eyebrow">Contract Review Workspace</p>
        <h1>合同审查工作台</h1>
        <p class="copy">
          在不影响原有知识库、检索和问答流程的前提下，集中完成合同上传、模板匹配、
          结构化审查、结果复核与 DOCX 导出。
        </p>
      </div>
      <div class="stats">
        <div class="stat">
          <span>模板库</span>
          <strong>{{ templates.length }} 个模板</strong>
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

    <div class="tabs">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="tab"
        :class="{ 'tab--active': activeTab === tab.key }"
        @click="activeTab = tab.key"
      >
        <UIcon :name="tab.icon" class="h-4 w-4" />
        {{ tab.label }}
      </button>
    </div>

    <section v-if="activeTab === 'launch'" class="grid-layout">
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
              <label>模板选择</label>
              <USelect
                v-model="selectedTemplateId"
                :items="
                  templates.map((item) => ({
                    label: item.name,
                    value: item.id,
                  }))
                "
                value-key="value"
                placeholder="请选择模板"
              />
            </div>
          </div>

          <div class="actions">
            <UButton
              color="neutral"
              variant="ghost"
              @click="activeTab = 'templates'"
              >管理模板</UButton
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

      <UCard class="card">
        <template #header>
          <div class="card-head">
            <div>
              <p class="eyebrow">Timeline</p>
              <h2>最近任务</h2>
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

        <div v-if="!jobs.length" class="empty">还没有合同审查任务。</div>
        <div v-else class="stack">
          <button
            v-for="job in jobs"
            :key="job.id"
            class="list-card"
            :class="{ 'list-card--active': selectedJob?.id === job.id }"
            @click="store.selectJob(job.id)"
          >
            <div class="card-head">
              <div>
                <p class="title">{{ job.review_name }}</p>
                <p class="subtle">
                  {{ job.template_name || "未命名模板" }} ·
                  {{ formatDate(job.created_at) }}
                </p>
              </div>
              <UBadge
                :color="getStatusColor(job.status) as any"
                variant="subtle"
                size="sm"
              >
                {{ getStatusLabel(job.status) }}
              </UBadge>
            </div>
            <p class="subtle">{{ job.original_filename }}</p>
          </button>
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
                {{ detail.template?.name || "未绑定模板" }}
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
              <p class="eyebrow">Queue</p>
              <h2>任务侧栏</h2>
            </div>
          </div>
        </template>
        <div class="stack">
          <button
            v-for="job in jobs"
            :key="job.id"
            class="list-card"
            :class="{ 'list-card--active': selectedJob?.id === job.id }"
            @click="store.selectJob(job.id)"
          >
            <div class="card-head">
              <p class="title">{{ job.review_name }}</p>
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
        </div>
      </UCard>
    </section>

    <section v-else class="grid-layout">
      <UCard class="card">
        <template #header>
          <div class="card-head">
            <div>
              <p class="eyebrow">Library</p>
              <h2>上传模板</h2>
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
              <p class="title">上传模板文件</p>
              <p class="subtle">自由上传模板，并绑定一个首轮审查配置。</p>
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
              <label>模板名称</label>
              <UInput v-model="templateForm.name" />
            </div>
            <div class="field">
              <label>模板分类</label>
              <UInput v-model="templateForm.category" />
            </div>
            <div class="field">
              <label>合同类型</label>
              <USelect
                v-model="templateForm.contractType"
                :items="profiles"
                value-key="value"
              />
            </div>
            <div class="field">
              <label>配置档位</label>
              <USelect
                v-model="templateForm.configProfile"
                :items="profiles"
                value-key="value"
              />
            </div>
          </div>

          <div class="field">
            <label>模板说明</label>
            <UTextarea v-model="templateForm.description" :rows="4" />
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
              上传模板
            </UButton>
          </div>
        </div>
      </UCard>

      <UCard class="card">
        <template #header>
          <div class="card-head">
            <div>
              <p class="eyebrow">Catalog</p>
              <h2>模板列表</h2>
            </div>
          </div>
        </template>

        <div v-if="!templates.length" class="empty">
          还没有模板，可以先上传团队模板。
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
                  {{ item.source_type === "seed" ? "种子模板" : "手动上传" }}
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
              {{ item.description || "当前模板已绑定默认审查配置。" }}
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
  display: grid;
  gap: 20px;
}
.hero,
.card,
.list-card,
.dropzone,
.pill,
.panel,
.stat,
.tab {
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
  gap: 24px;
  padding: 28px;
  background: linear-gradient(
    135deg,
    rgba(255, 255, 255, 0.96),
    rgba(250, 246, 238, 0.94)
  );
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
  margin-top: 14px;
  max-width: 860px;
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
  gap: 10px;
}
.tab {
  border-radius: 999px;
  padding: 10px 16px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #5a5a55;
  transition: 0.18s;
}
.tab--active {
  border-color: #3158ff;
  color: #3158ff;
  background: linear-gradient(135deg, #f8fbff, #fff);
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
    align-items: end;
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
