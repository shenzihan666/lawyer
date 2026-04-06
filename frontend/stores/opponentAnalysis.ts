import { defineStore } from "pinia";

export type OpponentAnalysisCitation = {
  citation_number: number;
  chunk_id: string;
  document_id: string;
  original_filename: string;
  page_number: number;
  snippet: string;
  score: number;
  metadata: Record<string, unknown>;
};

export type OpponentAnalysisAgentPayload = {
  claims: string[];
  likely_quotes: string[];
  likely_actions: string[];
  attack_points: string[];
  confidence: number;
  notes: string;
  citation_numbers: number[];
};

export type OpponentAnalysisEvidenceItem = {
  citation_number: number;
  chunk_id: string;
  document_id: string;
  original_filename: string;
  page_number: number;
  snippet: string;
  score: number;
  used_by: string[];
  phases: string[];
  metadata: Record<string, unknown>;
};

export type OpponentAnalysisSummary = {
  opponent_position: {
    summary: string;
    claims: string[];
    confidence: number;
  };
  lawyer_predictions: OpponentAnalysisAgentPayload;
  party_predictions: OpponentAnalysisAgentPayload;
  response_plan: {
    priority_actions: string[];
    courtroom_responses: string[];
    evidence_to_prepare: string[];
    notes: string;
  };
  evidence_index: OpponentAnalysisEvidenceItem[];
  risk_level: string;
};

export type OpponentAnalysisRunItem = {
  id: string;
  case_facts: string;
  case_facts_preview: string;
  top_k: number;
  scope_document_ids: string[];
  status: string;
  risk_level: string | null;
  failure_reason: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
};

export type OpponentAnalysisEventItem = {
  id: number;
  seq: number;
  phase: string;
  round: number;
  from_agent: string | null;
  to_agent: string | null;
  event_type: string;
  title: string;
  content: string;
  structured_payload: Record<string, unknown>;
  citations: OpponentAnalysisCitation[];
  status: string;
  created_at: string;
};

export type OpponentAnalysisDetail = {
  run: OpponentAnalysisRunItem;
  events: OpponentAnalysisEventItem[];
  summary: OpponentAnalysisSummary;
};

type StreamSnapshotEvent = {
  type: "snapshot";
  run: OpponentAnalysisRunItem;
  summary: OpponentAnalysisSummary;
  latest_seq: number;
};

type StreamEventPayload = {
  type: "event";
  event: OpponentAnalysisEventItem;
};

type StreamDoneEvent = {
  type: "done";
  run: OpponentAnalysisRunItem;
  summary: OpponentAnalysisSummary;
  latest_seq: number;
};

type OpponentAnalysisStreamPayload =
  | StreamSnapshotEvent
  | StreamEventPayload
  | StreamDoneEvent;

export const useOpponentAnalysisStore = defineStore("opponent-analysis", () => {
  const runtimeConfig = useRuntimeConfig();
  const apiBase = runtimeConfig.public.apiBase as string;
  const toast = useToast();

  const caseFacts = ref("");
  const topK = ref(5);
  const selectedDocumentIds = ref<string[]>([]);

  const runs = ref<OpponentAnalysisRunItem[]>([]);
  const detail = ref<OpponentAnalysisDetail | null>(null);
  const activeRunId = ref<string | null>(null);
  const activeTab = ref<"overview" | "process" | "speech" | "evidence">(
    "overview",
  );

  const isCreating = ref(false);
  const isLoadingHistory = ref(false);
  const isLoadingDetail = ref(false);
  const isStreaming = ref(false);

  const replayVisibleCount = ref<number | null>(null);
  const isReplayActive = computed(() => replayVisibleCount.value !== null);

  let streamController: AbortController | null = null;
  let streamRunId: string | null = null;
  let replayTimer: ReturnType<typeof setInterval> | null = null;

  const visibleEvents = computed(() => {
    const items = detail.value?.events ?? [];
    if (replayVisibleCount.value === null) {
      return items;
    }
    return items.slice(0, replayVisibleCount.value);
  });

  async function request<T>(
    path: string,
    options?: Parameters<typeof $fetch<T>>[1],
  ) {
    return await $fetch<T>(`${apiBase}${path}`, options);
  }

  function sortRuns(items: OpponentAnalysisRunItem[]) {
    return [...items].sort(
      (left, right) =>
        new Date(right.updated_at).getTime() -
        new Date(left.updated_at).getTime(),
    );
  }

  function upsertRun(run: OpponentAnalysisRunItem) {
    const next = [...runs.value];
    const index = next.findIndex((item) => item.id === run.id);
    if (index === -1) {
      runs.value = sortRuns([run, ...next]);
      return;
    }
    next[index] = { ...next[index], ...run };
    runs.value = sortRuns(next);
  }

  function stopStream() {
    streamController?.abort();
    streamController = null;
    streamRunId = null;
    isStreaming.value = false;
  }

  function stopReplay() {
    if (!replayTimer) return;
    clearInterval(replayTimer);
    replayTimer = null;
  }

  function resetReplay() {
    stopReplay();
    replayVisibleCount.value = null;
  }

  function startReplay() {
    const events = detail.value?.events ?? [];
    if (!events.length) return;
    stopReplay();
    replayVisibleCount.value = 0;
    activeTab.value = "process";
    replayTimer = setInterval(() => {
      const nextValue = (replayVisibleCount.value ?? 0) + 1;
      replayVisibleCount.value = nextValue;
      if (nextValue >= events.length) {
        resetReplay();
      }
    }, 360);
  }

  function applyDetail(payload: OpponentAnalysisDetail) {
    detail.value = {
      ...payload,
      events: [...payload.events].sort((left, right) => left.seq - right.seq),
    };
    activeRunId.value = payload.run.id;
    upsertRun(payload.run);
  }

  function mergeEvent(runId: string, event: OpponentAnalysisEventItem) {
    if (detail.value?.run.id !== runId) return;
    const next = [...detail.value.events];
    const index = next.findIndex((item) => item.seq === event.seq);
    if (index === -1) {
      next.push(event);
    } else {
      next[index] = event;
    }
    next.sort((left, right) => left.seq - right.seq);
    detail.value = {
      ...detail.value,
      events: next,
    };
  }

  function applyStreamPayload(
    runId: string,
    payload: OpponentAnalysisStreamPayload,
  ) {
    if (payload.type === "snapshot") {
      if (detail.value?.run.id === runId) {
        detail.value = {
          ...detail.value,
          run: payload.run,
          summary: payload.summary,
        };
      }
      upsertRun(payload.run);
      return;
    }

    if (payload.type === "event") {
      mergeEvent(runId, payload.event);
      return;
    }

    if (detail.value?.run.id === runId) {
      detail.value = {
        ...detail.value,
        run: payload.run,
        summary: payload.summary,
      };
    }
    upsertRun(payload.run);
  }

  function parseSseBlock(block: string) {
    const lines = block
      .replace(/\r/g, "")
      .split("\n")
      .filter((line) => line.startsWith("data:"));

    if (!lines.length) return null;
    return lines.map((line) => line.slice(5).trimStart()).join("\n");
  }

  async function fetchHistory() {
    isLoadingHistory.value = true;
    try {
      const payload = await request<{ items: OpponentAnalysisRunItem[] }>(
        "/opponent-analyses",
      );
      runs.value = sortRuns(payload.items ?? []);
      return runs.value;
    } catch (error) {
      toast.add({
        title: "预测历史加载失败",
        description: String(error),
        color: "error",
      });
      return [];
    } finally {
      isLoadingHistory.value = false;
    }
  }

  async function fetchDetail(runId: string, options?: { quiet?: boolean }) {
    if (!options?.quiet) {
      isLoadingDetail.value = true;
    }
    try {
      const payload = await request<OpponentAnalysisDetail>(
        `/opponent-analyses/${runId}`,
      );
      applyDetail(payload);
      resetReplay();
      await ensureStreaming(runId);
      return payload;
    } catch (error) {
      if (!options?.quiet) {
        toast.add({
          title: "预测详情加载失败",
          description: String(error),
          color: "error",
        });
      }
      throw error;
    } finally {
      if (!options?.quiet) {
        isLoadingDetail.value = false;
      }
    }
  }

  async function createRun() {
    if (!caseFacts.value.trim()) {
      toast.add({
        title: "请输入案情摘要",
        description: "至少提供一段能够支撑预测的案情描述。",
        color: "warning",
      });
      return;
    }

    isCreating.value = true;
    try {
      const payload = await request<OpponentAnalysisDetail>(
        "/opponent-analyses",
        {
          method: "POST",
          body: {
            case_facts: caseFacts.value.trim(),
            top_k: topK.value,
            document_ids: selectedDocumentIds.value,
          },
        },
      );
      applyDetail(payload);
      activeTab.value = "overview";
      resetReplay();
      await ensureStreaming(payload.run.id);
      toast.add({
        title: "预测任务已发起",
        description: "多智能体推演已经开始，过程会在右侧实时展开。",
        color: "success",
      });
      return payload;
    } catch (error) {
      toast.add({
        title: "发起预测失败",
        description: String(error),
        color: "error",
      });
      throw error;
    } finally {
      isCreating.value = false;
    }
  }

  async function ensureStreaming(runId: string) {
    const currentRun = detail.value?.run.id === runId ? detail.value.run : null;
    if (!currentRun) return;
    if (["completed", "failed"].includes(currentRun.status)) {
      stopStream();
      return;
    }
    if (streamRunId === runId && streamController) {
      return;
    }
    await streamRun(runId, detail.value?.events.at(-1)?.seq ?? 0);
  }

  async function streamRun(runId: string, afterSeq = 0) {
    stopStream();

    const controller = new AbortController();
    streamController = controller;
    streamRunId = runId;
    isStreaming.value = true;

    try {
      const response = await fetch(
        `${apiBase}/opponent-analyses/${runId}/stream?after_seq=${afterSeq}`,
        {
          signal: controller.signal,
        },
      );
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      if (!response.body) {
        throw new Error("Streaming response body is unavailable");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          buffer += decoder.decode();
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        let boundaryIndex = buffer.indexOf("\n\n");
        while (boundaryIndex !== -1) {
          const block = buffer.slice(0, boundaryIndex);
          buffer = buffer.slice(boundaryIndex + 2);
          const data = parseSseBlock(block);
          if (data) {
            if (data !== "[DONE]") {
              applyStreamPayload(
                runId,
                JSON.parse(data) as OpponentAnalysisStreamPayload,
              );
            }
          }
          boundaryIndex = buffer.indexOf("\n\n");
        }
      }

      const trailingData = parseSseBlock(buffer);
      if (trailingData && trailingData !== "[DONE]") {
        applyStreamPayload(
          runId,
          JSON.parse(trailingData) as OpponentAnalysisStreamPayload,
        );
      }
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) {
        toast.add({
          title: "预测流中断",
          description: String(error),
          color: "error",
        });
      }
    } finally {
      if (streamRunId === runId) {
        streamController = null;
        streamRunId = null;
        isStreaming.value = false;
      }
    }
  }

  async function selectRun(runId: string) {
    await fetchDetail(runId);
  }

  async function deleteRun(runId: string) {
    try {
      await request(`/opponent-analyses/${runId}`, { method: "DELETE" });
      runs.value = runs.value.filter((item) => item.id !== runId);
      if (detail.value?.run.id === runId) {
        stopStream();
        detail.value = null;
        activeRunId.value = null;
        resetReplay();
      }
      toast.add({
        title: "预测历史已删除",
        description: "该次多智能体推演记录已移除。",
        color: "success",
      });
    } catch (error) {
      toast.add({
        title: "删除失败",
        description: String(error),
        color: "error",
      });
    }
  }

  function resetComposer() {
    caseFacts.value = "";
    topK.value = 5;
    selectedDocumentIds.value = [];
  }

  function dispose() {
    stopStream();
    resetReplay();
  }

  return {
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
    fetchHistory,
    fetchDetail,
    createRun,
    selectRun,
    deleteRun,
    startReplay,
    resetReplay,
    resetComposer,
    dispose,
  };
});
