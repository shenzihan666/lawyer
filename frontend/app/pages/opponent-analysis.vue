<script setup lang="ts">
import { storeToRefs } from "pinia";
import { useDocumentStore } from "../../stores/documents";
import {
  type OpponentAnalysisCitation,
  type OpponentAnalysisSummary,
  useOpponentAnalysisStore,
} from "../../stores/opponentAnalysis";

type AgentKey =
  | "opponent_party"
  | "opponent_counsel"
  | "bench_observer"
  | "our_strategy_advisor";

type EvidenceRow = OpponentAnalysisCitation & {
  phases: string[];
  agents: string[];
};

const store = useOpponentAnalysisStore();
const documentStore = useDocumentStore();

const { documents } = storeToRefs(documentStore);
const {
  caseFacts,
  topK,
  selectedDocumentIds,
  runs,
  detail,
  activeRunId,
  activeTab,
  isCreating,
  isLoadingHistory,
  isLoadingDetail,
  isStreaming,
  visibleEvents,
  isReplayActive,
} = storeToRefs(store);

const tabs = [
  { key: "overview", label: "预测总览", icon: "i-lucide-layout-dashboard" },
  { key: "process", label: "多智能体过程", icon: "i-lucide-waypoints" },
  { key: "speech", label: "话术与行为", icon: "i-lucide-messages-square" },
  { key: "evidence", label: "证据依据", icon: "i-lucide-library-big" },
] as const;

const topKOptions = [3, 5, 7, 10].map((value) => ({
  label: `${value} 条`,
  value,
}));
const lanes = [
  { key: "opponent_party", label: "对方当事人", icon: "i-lucide-user-round" },
  {
    key: "opponent_counsel",
    label: "对方律师",
    icon: "i-lucide-briefcase-business",
  },
  { key: "bench_observer", label: "庭审观察员", icon: "i-lucide-scale" },
  {
    key: "our_strategy_advisor",
    label: "我方策略官",
    icon: "i-lucide-shield-check",
  },
] as const;
const phaseLabels: Record<string, string> = {
  context_brief: "共享证据整理",
  party_projection: "对方当事人投射",
  counsel_projection: "对方律师投射",
  bench_review: "庭审观察校准",
  strategy_response: "我方策略回应",
  revision: "接收消息后修正",
  finalize: "形成最终看板",
};

const evidenceAgentFilter = ref("all");
const evidencePhaseFilter = ref("all");

const indexedDocuments = computed(() =>
  documents.value.filter((item) => item.vector_status === "indexed"),
);
const selectedDocuments = computed(() =>
  indexedDocuments.value.filter((item) =>
    selectedDocumentIds.value.includes(item.id),
  ),
);
const activeRun = computed(() => detail.value?.run ?? null);
const summary = computed<OpponentAnalysisSummary>(() => {
  if (detail.value?.summary) return detail.value.summary;
  return {
    opponent_position: { summary: "", claims: [], confidence: 0 },
    lawyer_predictions: {
      claims: [],
      likely_quotes: [],
      likely_actions: [],
      attack_points: [],
      confidence: 0,
      notes: "",
      citation_numbers: [],
    },
    party_predictions: {
      claims: [],
      likely_quotes: [],
      likely_actions: [],
      attack_points: [],
      confidence: 0,
      notes: "",
      citation_numbers: [],
    },
    response_plan: {
      priority_actions: [],
      courtroom_responses: [],
      evidence_to_prepare: [],
      notes: "",
    },
    evidence_index: [],
    risk_level: "pending",
  };
});

const evidenceRows = computed<EvidenceRow[]>(() => {
  const map = new Map<
    string,
    { row: OpponentAnalysisCitation; phases: Set<string>; agents: Set<string> }
  >();
  for (const event of detail.value?.events ?? []) {
    for (const citation of event.citations) {
      const current = map.get(citation.chunk_id) ?? {
        row: citation,
        phases: new Set<string>(),
        agents: new Set<string>(),
      };
      current.phases.add(event.phase);
      current.agents.add(event.from_agent || "shared_context");
      map.set(citation.chunk_id, current);
    }
  }
  return [...map.values()].map((item) => ({
    ...item.row,
    phases: [...item.phases],
    agents: [...item.agents],
  }));
});

const filteredEvidenceRows = computed(() =>
  evidenceRows.value.filter((item) => {
    const byAgent =
      evidenceAgentFilter.value === "all" ||
      item.agents.includes(evidenceAgentFilter.value);
    const byPhase =
      evidencePhaseFilter.value === "all" ||
      item.phases.includes(evidencePhaseFilter.value);
    return byAgent && byPhase;
  }),
);

const speechColumns = computed(() => [
  {
    title: "对方律师",
    quote: summary.value.lawyer_predictions.likely_quotes,
    action: summary.value.lawyer_predictions.likely_actions,
    attack: summary.value.lawyer_predictions.attack_points,
    prepare: summary.value.response_plan.priority_actions,
  },
  {
    title: "对方当事人",
    quote: summary.value.party_predictions.likely_quotes,
    action: summary.value.party_predictions.likely_actions,
    attack: summary.value.party_predictions.attack_points,
    prepare: summary.value.response_plan.evidence_to_prepare,
  },
  {
    title: "我方应对",
    quote: summary.value.response_plan.courtroom_responses,
    action: summary.value.response_plan.priority_actions,
    attack: [
      ...summary.value.lawyer_predictions.attack_points,
      ...summary.value.party_predictions.attack_points,
    ].filter((item, index, arr) => arr.indexOf(item) === index),
    prepare: summary.value.response_plan.evidence_to_prepare,
  },
]);

onMounted(async () => {
  await Promise.all([documentStore.refreshDocuments(), store.fetchHistory()]);
  if (runs.value[0]?.id) {
    await store.fetchDetail(runs.value[0].id, { quiet: true });
  }
});

onBeforeUnmount(() => store.dispose());

function labelStatus(status: string) {
  return (
    {
      queued: "排队中",
      running: "推演中",
      completed: "已完成",
      failed: "失败",
    }[status] || status
  );
}
function labelRisk(level: string) {
  return (
    { low: "低", medium: "中", high: "高", pending: "待生成" }[level] || level
  );
}
function labelPhase(phase: string) {
  return phaseLabels[phase] || phase;
}
function labelAgent(agent: string | null) {
  return lanes.find((item) => item.key === agent)?.label || "系统编排";
}
function laneClass(agent: string | null) {
  const index = lanes.findIndex((item) => item.key === agent);
  return index === -1 ? "process-card--system" : `process-card--lane-${index}`;
}
function formatDate(value: string | null) {
  if (!value) return "进行中";
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
function formatConfidence(value: number) {
  return `${Math.round((value || 0) * 100)}%`;
}
function formatScore(score: number) {
  return score.toFixed(3);
}
function toggleDocument(id: string) {
  selectedDocumentIds.value = selectedDocumentIds.value.includes(id)
    ? selectedDocumentIds.value.filter((item) => item !== id)
    : [...selectedDocumentIds.value, id];
}
function toggleAllDocuments() {
  selectedDocumentIds.value =
    selectedDocumentIds.value.length === indexedDocuments.value.length
      ? []
      : indexedDocuments.value.map((item) => item.id);
}
async function createRun() {
  await store.createRun();
}
async function selectRun(runId: string) {
  activeTab.value = "overview";
  await store.selectRun(runId);
}
async function deleteRun(runId: string) {
  if (!window.confirm("删除后将移除此推演历史，确定继续吗？")) return;
  await store.deleteRun(runId);
  if (!detail.value && runs.value[0]?.id)
    await store.selectRun(runs.value[0].id);
}
</script>

<template>
  <div class="oa-page px-4 py-6 md:px-8 md:py-8">
    <section class="oa-hero">
      <div>
        <p class="eyebrow">Opponent Analysis Board</p>
        <h1>对方观点预测多智能体看板</h1>
        <p class="copy">
          基于案情摘要与已索引文档，按四角编排接力推演，并把全过程沉淀为可追流、可回放的事件时间线。
        </p>
      </div>
      <div class="hero-stats">
        <div class="mini-card">
          <span>已索引文档</span><strong>{{ indexedDocuments.length }}</strong>
        </div>
        <div class="mini-card">
          <span>推演历史</span><strong>{{ runs.length }}</strong>
        </div>
        <div class="mini-card">
          <span>当前范围</span
          ><strong>{{ selectedDocuments.length || "全库" }}</strong>
        </div>
      </div>
    </section>

    <div class="oa-layout">
      <aside class="oa-side">
        <section class="panel">
          <div class="head">
            <div>
              <p class="eyebrow">Launch</p>
              <h2>发起预测</h2>
            </div>
            <span class="pill">{{
              selectedDocuments.length
                ? `已选 ${selectedDocuments.length}`
                : "全库"
            }}</span>
          </div>

          <label class="field">
            <span>案情摘要</span>
            <textarea
              v-model="caseFacts"
              rows="7"
              class="case-input"
              placeholder="输入案情关键事实、争议焦点、时间线、金额与证据缺口。"
            />
          </label>

          <div class="field-row">
            <label class="field">
              <span>检索条数</span>
              <USelect v-model="topK" :items="topKOptions" value-key="value" />
            </label>
            <div class="field note">
              页面只展示预测、可能与建议，不把推演结果包装成事实。
            </div>
          </div>

          <div class="head head--compact">
            <span>文档范围</span>
            <UButton
              size="xs"
              color="neutral"
              variant="ghost"
              :disabled="!indexedDocuments.length"
              @click="toggleAllDocuments"
            >
              {{
                selectedDocumentIds.length === indexedDocuments.length
                  ? "取消全选"
                  : "全选"
              }}
            </UButton>
          </div>
          <div v-if="!indexedDocuments.length" class="empty">
            当前没有已索引文档。
          </div>
          <div v-else class="doc-list">
            <button
              v-for="item in indexedDocuments"
              :key="item.id"
              class="doc-item"
              :class="{
                'doc-item--active': selectedDocumentIds.includes(item.id),
              }"
              @click="toggleDocument(item.id)"
            >
              <span>{{ item.original_filename }}</span>
              <small>{{ item.page_count || 0 }} 页</small>
            </button>
          </div>

          <div class="actions">
            <UButton
              color="neutral"
              variant="ghost"
              @click="store.resetComposer()"
              >清空</UButton
            >
            <UButton
              color="primary"
              :loading="isCreating"
              :disabled="!caseFacts.trim()"
              @click="createRun"
              >发起预测</UButton
            >
          </div>
        </section>

        <section class="panel">
          <div class="head">
            <div>
              <p class="eyebrow">History</p>
              <h2>历史回放</h2>
            </div>
            <UButton
              icon="i-lucide-refresh-cw"
              color="neutral"
              variant="ghost"
              :loading="isLoadingHistory"
              @click="store.fetchHistory()"
            />
          </div>
          <div v-if="!runs.length" class="empty">还没有推演历史。</div>
          <div v-else class="history-list">
            <article
              v-for="run in runs"
              :key="run.id"
              class="history-item"
              :class="{ 'history-item--active': activeRunId === run.id }"
            >
              <button class="history-button" @click="selectRun(run.id)">
                <div class="history-top">
                  <span class="pill">{{ labelStatus(run.status) }}</span
                  ><small>{{ formatDate(run.updated_at) }}</small>
                </div>
                <p>{{ run.case_facts_preview }}</p>
              </button>
              <UButton
                icon="i-lucide-trash-2"
                color="error"
                variant="ghost"
                size="xs"
                @click.stop="deleteRun(run.id)"
              />
            </article>
          </div>
        </section>
      </aside>

      <section class="oa-main">
        <header class="main-head">
          <div>
            <div class="status-row">
              <span
                class="dot"
                :class="{
                  'dot--live': isStreaming || activeRun?.status === 'running',
                }"
              />
              <span class="pill">{{
                activeRun ? labelStatus(activeRun.status) : "等待发起"
              }}</span>
              <span v-if="isStreaming" class="pill">实时追流中</span>
            </div>
            <h2>
              {{ activeRun ? "当前预测运行" : "等待创建或选择一条运行记录" }}
            </h2>
            <p class="copy">
              {{
                activeRun?.failure_reason ||
                "以下内容仅用于预测、可能性判断和庭审准备建议。"
              }}
            </p>
          </div>
          <div v-if="activeRun" class="meta">
            <div class="mini-card">
              <span>创建时间</span
              ><strong>{{ formatDate(activeRun.created_at) }}</strong>
            </div>
            <div class="mini-card">
              <span>完成时间</span
              ><strong>{{ formatDate(activeRun.completed_at) }}</strong>
            </div>
          </div>
        </header>

        <div class="tabs">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            class="tab"
            :class="{ 'tab--active': activeTab === tab.key }"
            @click="activeTab = tab.key"
          >
            <UIcon :name="tab.icon" class="h-4 w-4" />
            <span>{{ tab.label }}</span>
          </button>
        </div>

        <div class="body">
          <div v-if="isLoadingDetail" class="empty">正在载入预测详情……</div>
          <div v-else-if="!detail" class="empty">
            右侧会显示总览、过程泳道、话术行为与证据依据。
          </div>

          <template v-else>
            <section v-if="activeTab === 'overview'" class="stack">
              <div class="warn">
                以下内容仅用于预测、可能与建议，不构成事实认定或法律结论。
              </div>
              <div class="hero-summary">
                <div>
                  <p class="eyebrow">Opponent Position</p>
                  <h3>对方总体立场</h3>
                  <p>
                    {{
                      summary.opponent_position.summary ||
                      "推演尚未形成稳定总结。"
                    }}
                  </p>
                </div>
                <div class="summary-score">
                  {{ formatConfidence(summary.opponent_position.confidence) }}
                </div>
              </div>
              <div class="grid4">
                <div class="mini-card">
                  <span>风险等级</span
                  ><strong>{{ labelRisk(summary.risk_level) }}</strong>
                </div>
                <div class="mini-card">
                  <span>律师置信度</span
                  ><strong>{{
                    formatConfidence(summary.lawyer_predictions.confidence)
                  }}</strong>
                </div>
                <div class="mini-card">
                  <span>当事人置信度</span
                  ><strong>{{
                    formatConfidence(summary.party_predictions.confidence)
                  }}</strong>
                </div>
                <div class="mini-card">
                  <span>实际证据</span
                  ><strong>{{ evidenceRows.length }} 条</strong>
                </div>
              </div>
              <div class="grid2">
                <div class="panel">
                  <h3>最可能的三条主张</h3>
                  <ul class="list">
                    <li
                      v-for="item in summary.opponent_position.claims"
                      :key="item"
                    >
                      {{ item }}
                    </li>
                  </ul>
                </div>
                <div class="panel">
                  <h3>最可能的庭审动作</h3>
                  <ul class="list">
                    <li
                      v-for="item in summary.lawyer_predictions.likely_actions"
                      :key="item"
                    >
                      {{ item }}
                    </li>
                  </ul>
                </div>
                <div class="panel">
                  <h3>我方优先准备事项</h3>
                  <ul class="list">
                    <li
                      v-for="item in summary.response_plan.priority_actions"
                      :key="item"
                    >
                      {{ item }}
                    </li>
                  </ul>
                </div>
                <div class="panel">
                  <h3>补强证据与备注</h3>
                  <ul class="list">
                    <li
                      v-for="item in summary.response_plan.evidence_to_prepare"
                      :key="item"
                    >
                      {{ item }}
                    </li>
                  </ul>
                  <p class="copy">{{ summary.response_plan.notes }}</p>
                </div>
              </div>
            </section>

            <section v-else-if="activeTab === 'process'" class="stack">
              <div class="lane-head">
                <div
                  v-for="lane in lanes"
                  :key="lane.key"
                  class="mini-card lane-card"
                >
                  <UIcon :name="lane.icon" class="h-4 w-4" /><strong>{{
                    lane.label
                  }}</strong>
                </div>
              </div>
              <div class="actions">
                <UButton
                  icon="i-lucide-refresh-cw"
                  color="neutral"
                  variant="ghost"
                  @click="activeRun && store.fetchDetail(activeRun.id)"
                  >刷新</UButton
                >
                <UButton
                  v-if="
                    activeRun &&
                    ['completed', 'failed'].includes(activeRun.status) &&
                    detail.events.length
                  "
                  icon="i-lucide-history"
                  color="primary"
                  variant="soft"
                  @click="
                    isReplayActive ? store.resetReplay() : store.startReplay()
                  "
                >
                  {{ isReplayActive ? "停止回放" : "回放过程" }}
                </UButton>
              </div>
              <div class="process-grid">
                <article
                  v-for="event in visibleEvents"
                  :key="event.seq"
                  class="process-card"
                  :class="laneClass(event.from_agent)"
                >
                  <div class="history-top">
                    <strong>{{ labelAgent(event.from_agent) }}</strong>
                    <span class="pill">{{ labelPhase(event.phase) }}</span>
                  </div>
                  <p class="process-title">{{ event.title }}</p>
                  <p class="copy">{{ event.content }}</p>
                  <div class="process-meta">
                    <span>第 {{ event.round }} 轮</span>
                    <span>{{ event.citations.length }} 条证据</span>
                    <span>#{{ event.seq }}</span>
                  </div>
                </article>
              </div>
            </section>

            <section v-else-if="activeTab === 'speech'" class="speech-grid">
              <article
                v-for="column in speechColumns"
                :key="column.title"
                class="panel"
              >
                <h3>{{ column.title }}</h3>
                <div class="speech-block">
                  <h4>可能会说</h4>
                  <ul class="list">
                    <li v-for="item in column.quote" :key="item">{{ item }}</li>
                  </ul>
                </div>
                <div class="speech-block">
                  <h4>可能会做</h4>
                  <ul class="list">
                    <li v-for="item in column.action" :key="item">
                      {{ item }}
                    </li>
                  </ul>
                </div>
                <div class="speech-block">
                  <h4>可能攻击的证据点</h4>
                  <ul class="list">
                    <li v-for="item in column.attack" :key="item">
                      {{ item }}
                    </li>
                  </ul>
                </div>
                <div class="speech-block">
                  <h4>建议准备</h4>
                  <ul class="list">
                    <li v-for="item in column.prepare" :key="item">
                      {{ item }}
                    </li>
                  </ul>
                </div>
              </article>
            </section>

            <section v-else class="stack">
              <div class="field-row">
                <USelect
                  v-model="evidenceAgentFilter"
                  :items="[
                    { label: '全部角色', value: 'all' },
                    ...lanes.map((item) => ({
                      label: item.label,
                      value: item.key,
                    })),
                  ]"
                  value-key="value"
                />
                <USelect
                  v-model="evidencePhaseFilter"
                  :items="[
                    { label: '全部阶段', value: 'all' },
                    ...Object.entries(phaseLabels).map(([value, label]) => ({
                      label,
                      value,
                    })),
                  ]"
                  value-key="value"
                />
              </div>
              <div v-if="!filteredEvidenceRows.length" class="empty">
                当前筛选条件下没有证据卡片。
              </div>
              <div v-else class="grid2">
                <article
                  v-for="item in filteredEvidenceRows"
                  :key="item.chunk_id"
                  class="panel"
                >
                  <div class="history-top">
                    <strong>{{ item.original_filename }}</strong
                    ><span class="pill">[{{ item.citation_number }}]</span>
                  </div>
                  <p class="copy">{{ item.snippet }}</p>
                  <p class="copy">
                    第 {{ item.page_number || 0 }} 页 · score
                    {{ formatScore(item.score) }}
                  </p>
                  <div class="tag-row">
                    <span
                      v-for="phase in item.phases"
                      :key="phase"
                      class="tag"
                      >{{ labelPhase(phase) }}</span
                    >
                  </div>
                </article>
              </div>
            </section>
          </template>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.oa-page {
  min-height: 100vh;
  background:
    radial-gradient(
      circle at top left,
      rgba(255, 220, 188, 0.35),
      transparent 24%
    ),
    radial-gradient(
      circle at right top,
      rgba(200, 216, 255, 0.35),
      transparent 20%
    ),
    linear-gradient(180deg, #f5efe5, #fbfaf7);
  color: #241d17;
}
.oa-hero,
.panel,
.oa-main,
.mini-card,
.warn,
.empty,
.hero-summary,
.process-card,
.doc-item,
.history-item,
.tabs {
  border: 1px solid #eadfce;
  background: rgba(255, 255, 255, 0.86);
  box-shadow: 0 20px 44px rgba(38, 27, 17, 0.08);
}
.oa-hero,
.panel,
.oa-main,
.hero-summary,
.empty {
  border-radius: 28px;
}
.oa-hero {
  display: grid;
  gap: 16px;
  margin-bottom: 18px;
  padding: 24px;
}
.eyebrow {
  font-size: 11px;
  letter-spacing: 0.24em;
  text-transform: uppercase;
  color: #8d7e6f;
}
h1,
h2,
h3 {
  font-family: "Noto Serif SC", "Source Han Serif SC", "Songti SC", serif;
}
h1 {
  margin-top: 10px;
  font-size: clamp(2rem, 3vw, 3rem);
  line-height: 1.04;
}
.copy {
  color: #6c645b;
  line-height: 1.8;
}
.hero-stats,
.grid4,
.grid2,
.field-row,
.oa-layout,
.speech-grid,
.stack {
  display: grid;
  gap: 14px;
}
.mini-card {
  border-radius: 20px;
  padding: 14px;
}
.mini-card span {
  display: block;
  font-size: 12px;
  color: #8d7e6f;
}
.mini-card strong {
  display: block;
  margin-top: 8px;
}
.oa-side {
  display: grid;
  gap: 18px;
  align-content: start;
}
.panel {
  padding: 20px;
}
.head,
.actions,
.history-top,
.status-row,
.tag-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.head {
  margin-bottom: 14px;
}
.head--compact {
  margin: 8px 0;
}
.field {
  display: grid;
  gap: 8px;
}
.field span {
  font-size: 0.84rem;
  font-weight: 700;
  color: #4a4139;
}
.note,
.warn,
.empty {
  padding: 14px 16px;
  border-radius: 18px;
  line-height: 1.75;
  color: #6c645b;
}
.note,
.empty {
  background: rgba(255, 250, 244, 0.88);
}
.warn {
  background: rgba(255, 248, 235, 0.94);
  color: #89531a;
}
.case-input {
  resize: vertical;
  border: 1px solid #eadfce;
  border-radius: 20px;
  padding: 14px 16px;
  background: #fffdf9;
  min-height: 160px;
  outline: none;
}
.doc-list,
.history-list {
  display: grid;
  gap: 10px;
}
.doc-item,
.history-button {
  border: none;
  text-align: left;
  width: 100%;
}
.doc-item {
  border-radius: 16px;
  padding: 12px 14px;
  display: flex;
  justify-content: space-between;
  gap: 10px;
}
.doc-item--active,
.history-item--active {
  background: linear-gradient(180deg, #f7f9ff, #fff);
  border-color: rgba(49, 88, 255, 0.28);
}
.doc-item small,
.process-meta span,
.history-top small {
  color: #7c7369;
}
.history-item {
  border-radius: 20px;
  padding: 12px;
  display: flex;
  gap: 10px;
}
.history-button {
  display: grid;
  gap: 8px;
  background: transparent;
  padding: 0;
}
.pill,
.tag {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 5px 10px;
  font-size: 0.78rem;
  font-weight: 700;
  background: #f7f2e9;
  color: #6e5739;
}
.oa-main {
  min-height: calc(100vh - 13rem);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.main-head {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 16px;
  padding: 22px 24px 18px;
  border-bottom: 1px solid #eadfce;
}
.main-head h2 {
  margin-top: 12px;
  font-size: 1.6rem;
}
.meta {
  display: grid;
  gap: 10px;
  min-width: min(100%, 280px);
}
.dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: #bbb0a4;
}
.dot--live {
  background: #3158ff;
  box-shadow: 0 0 0 4px rgba(49, 88, 255, 0.12);
}
.tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 14px 24px 0;
  padding: 8px;
  border-radius: 24px;
}
.tab {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  border: none;
  border-radius: 18px;
  background: transparent;
  color: #5e564d;
  font-weight: 600;
}
.tab--active {
  background: #eef2ff;
  color: #3158ff;
}
.body {
  flex: 1;
  overflow: auto;
  padding: 18px 24px 24px;
}
.hero-summary {
  display: grid;
  gap: 16px;
  padding: 20px;
  background: linear-gradient(
    135deg,
    rgba(33, 27, 22, 0.96),
    rgba(60, 44, 28, 0.93)
  );
  color: #fff;
}
.hero-summary p,
.hero-summary .eyebrow {
  color: rgba(255, 255, 255, 0.78);
}
.summary-score {
  font-size: 1.8rem;
  font-weight: 700;
}
.list {
  padding-left: 1.1rem;
  display: grid;
  gap: 8px;
  color: #403831;
  line-height: 1.75;
}
.lane-head {
  display: grid;
  gap: 12px;
}
.lane-card {
  display: flex;
  align-items: center;
  gap: 10px;
}
.process-grid {
  display: grid;
  gap: 12px;
}
.process-card {
  border-radius: 20px;
  padding: 16px;
}
.process-card--system {
  background: linear-gradient(135deg, #f7f9ff, #fff);
}
.process-title {
  margin: 10px 0;
  font-weight: 700;
}
.process-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 10px;
  font-size: 0.8rem;
}
.speech-grid {
  align-items: start;
}
.speech-block {
  border-top: 1px dashed rgba(184, 116, 47, 0.22);
  padding-top: 12px;
  margin-top: 12px;
}
@media (min-width: 960px) {
  .oa-hero {
    grid-template-columns: minmax(0, 1.6fr) 320px;
  }
  .hero-stats,
  .grid4 {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .oa-layout {
    grid-template-columns: 360px minmax(0, 1fr);
    align-items: start;
  }
  .grid2 {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .speech-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .lane-head,
  .process-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
  .process-card--system {
    grid-column: 1 / -1;
  }
  .process-card--lane-0 {
    grid-column: 1;
  }
  .process-card--lane-1 {
    grid-column: 2;
  }
  .process-card--lane-2 {
    grid-column: 3;
  }
  .process-card--lane-3 {
    grid-column: 4;
  }
}
</style>
