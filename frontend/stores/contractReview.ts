import { defineStore } from "pinia";

export type ReviewTemplateItem = {
  id: string;
  name: string;
  category: string;
  contract_type: string;
  description: string | null;
  source_type: string;
  original_filename: string;
  stored_filename: string;
  storage_path: string;
  file_extension: string;
  mime_type: string | null;
  sha256: string;
  file_size: number;
  is_active: boolean;
  config_json: Record<string, unknown>;
  metadata_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
};

export type ReviewJobItem = {
  id: string;
  template_id: string;
  review_name: string;
  status: string;
  original_filename: string;
  stored_filename: string;
  storage_path: string;
  file_extension: string;
  mime_type: string | null;
  sha256: string;
  file_size: number;
  summary_json: Record<string, number>;
  result_snapshot_json: Record<string, unknown>;
  metadata_json: Record<string, unknown>;
  failure_reason: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  template_name: string | null;
};

export type ReviewClause = {
  id: number;
  review_job_id: string;
  clause_path: string;
  title: string;
  clause_index: number;
  page_start: number;
  page_end: number;
  content: string;
  metadata_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type ReviewFinding = {
  id: number;
  review_job_id: string;
  clause_id: number | null;
  checklist_key: string;
  title: string;
  severity: string;
  status: string;
  issue: string;
  evidence: string | null;
  rewrite_suggestion: string | null;
  sort_order: number;
  metadata_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  clause_title: string | null;
  clause_path: string | null;
  page_start: number | null;
  page_end: number | null;
};

export type ReviewChecklistSummary = {
  total: number;
  passed: number;
  warnings: number;
  failed: number;
  missing: number;
  high_risk: number;
  medium_risk: number;
  low_risk: number;
};

export type ReviewJobDetail = {
  job: ReviewJobItem;
  template: ReviewTemplateItem | null;
  clauses: ReviewClause[];
  findings: ReviewFinding[];
  checklist: ReviewChecklistSummary;
  export: {
    available: boolean;
    filename: string | null;
    url: string | null;
  };
  extensions: Record<string, unknown>;
};

type ReviewTemplateListResponse = {
  items: ReviewTemplateItem[];
  affected_ids?: string[];
};

type ReviewJobListResponse = {
  items: ReviewJobItem[];
};

type ReviewJobOperationResponse = ReviewJobListResponse & {
  affected_ids?: string[];
};

export const useContractReviewStore = defineStore("contractReview", () => {
  const runtimeConfig = useRuntimeConfig();
  const apiBase = runtimeConfig.public.apiBase as string;
  const toast = useToast();

  const templates = ref<ReviewTemplateItem[]>([]);
  const jobs = ref<ReviewJobItem[]>([]);
  const activeJobId = ref<string | null>(null);
  const activeTab = ref<
    "launch" | "results" | "template-upload" | "template-list"
  >("launch");
  const detail = ref<ReviewJobDetail | null>(null);

  const isLoadingTemplates = ref(false);
  const isLoadingJobs = ref(false);
  const isLoadingDetail = ref(false);
  const isCreatingJob = ref(false);
  const isUploadingTemplate = ref(false);
  const deletingTemplateIds = ref<string[]>([]);
  const deletingJobIds = ref<string[]>([]);

  let pollTimer: ReturnType<typeof setInterval> | null = null;

  async function request<T>(
    path: string,
    options?: Parameters<typeof $fetch<T>>[1],
  ) {
    return await $fetch<T>(`${apiBase}${path}`, options);
  }

  function stopPolling() {
    if (!pollTimer) return;
    clearInterval(pollTimer);
    pollTimer = null;
  }

  function startPolling(jobId: string) {
    stopPolling();
    pollTimer = setInterval(() => {
      void fetchJobDetail(jobId, { quiet: true });
    }, 1600);
  }

  async function fetchTemplates() {
    isLoadingTemplates.value = true;
    try {
      const payload = await request<ReviewTemplateListResponse>(
        "/contract-review/templates",
      );
      templates.value = payload.items;
    } catch (error) {
      toast.add({
        title: "模板加载失败",
        description: String(error),
        color: "error",
      });
    } finally {
      isLoadingTemplates.value = false;
    }
  }

  async function fetchJobs() {
    isLoadingJobs.value = true;
    try {
      const payload = await request<ReviewJobListResponse>(
        "/contract-review/jobs",
      );
      jobs.value = payload.items;
      const firstJob = payload.items[0];
      if (!activeJobId.value && firstJob) {
        activeJobId.value = firstJob.id;
      }
    } catch (error) {
      toast.add({
        title: "任务加载失败",
        description: String(error),
        color: "error",
      });
    } finally {
      isLoadingJobs.value = false;
    }
  }

  async function fetchJobDetail(jobId: string, options?: { quiet?: boolean }) {
    if (!options?.quiet) {
      isLoadingDetail.value = true;
    }

    try {
      const payload = await request<ReviewJobDetail>(
        `/contract-review/jobs/${jobId}`,
      );
      detail.value = payload;
      activeJobId.value = payload.job.id;
      const targetIndex = jobs.value.findIndex(
        (item) => item.id === payload.job.id,
      );
      if (targetIndex !== -1) {
        jobs.value[targetIndex] = payload.job;
      } else {
        jobs.value = [payload.job, ...jobs.value];
      }

      if (["queued", "running"].includes(payload.job.status)) {
        startPolling(payload.job.id);
      } else {
        stopPolling();
      }
      return payload;
    } catch (error) {
      if (!options?.quiet) {
        toast.add({
          title: "审查结果加载失败",
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

  async function createReviewJob(payload: {
    file: File;
    templateId: string;
    reviewName: string;
  }) {
    const formData = new FormData();
    formData.append("file", payload.file);
    formData.append("template_id", payload.templateId);
    if (payload.reviewName.trim()) {
      formData.append("review_name", payload.reviewName.trim());
    }

    isCreatingJob.value = true;
    try {
      const response = await request<ReviewJobDetail>("/contract-review/jobs", {
        method: "POST",
        body: formData,
      });
      detail.value = response;
      activeJobId.value = response.job.id;
      jobs.value = [
        response.job,
        ...jobs.value.filter((item) => item.id !== response.job.id),
      ];
      activeTab.value = "results";
      startPolling(response.job.id);
      toast.add({
        title: "审查任务已创建",
        description: "系统正在解析合同并生成结构化结果。",
        color: "success",
      });
      return response;
    } catch (error) {
      toast.add({
        title: "创建审查任务失败",
        description: String(error),
        color: "error",
      });
      throw error;
    } finally {
      isCreatingJob.value = false;
    }
  }

  async function uploadTemplate(payload: {
    file: File;
    name: string;
    category: string;
    contractType: string;
    description: string;
    configProfile: string;
  }) {
    const formData = new FormData();
    formData.append("file", payload.file);
    formData.append("name", payload.name.trim());
    formData.append("category", payload.category.trim());
    formData.append("contract_type", payload.contractType.trim());
    formData.append("description", payload.description.trim());
    formData.append("config_profile", payload.configProfile);

    isUploadingTemplate.value = true;
    try {
      const response = await request<ReviewTemplateListResponse>(
        "/contract-review/templates/upload",
        {
          method: "POST",
          body: formData,
        },
      );
      templates.value = response.items;
      toast.add({
        title: "模板已入库",
        description: "模板已经加入工作台模板库。",
        color: "success",
      });
    } catch (error) {
      toast.add({
        title: "模板上传失败",
        description: String(error),
        color: "error",
      });
      throw error;
    } finally {
      isUploadingTemplate.value = false;
    }
  }

  async function deleteTemplate(templateId: string) {
    deletingTemplateIds.value = [...deletingTemplateIds.value, templateId];
    try {
      const response = await request<ReviewTemplateListResponse>(
        `/contract-review/templates/${templateId}`,
        {
          method: "DELETE",
        },
      );
      templates.value = response.items;
      toast.add({
        title: "模板已删除",
        description: "模板已从工作台模板库移除。",
        color: "success",
      });
    } catch (error) {
      toast.add({
        title: "模板删除失败",
        description: String(error),
        color: "error",
      });
    } finally {
      deletingTemplateIds.value = deletingTemplateIds.value.filter(
        (id) => id !== templateId,
      );
    }
  }

  async function deleteJob(jobId: string) {
    deletingJobIds.value = [...deletingJobIds.value, jobId];
    const isCurrentJob =
      activeJobId.value === jobId || detail.value?.job.id === jobId;

    try {
      const response = await request<ReviewJobOperationResponse>(
        `/contract-review/jobs/${jobId}`,
        {
          method: "DELETE",
        },
      );
      jobs.value = response.items;

      if (isCurrentJob) {
        stopPolling();
        detail.value = null;
        activeJobId.value = jobs.value[0]?.id ?? null;
        if (activeJobId.value) {
          await fetchJobDetail(activeJobId.value, { quiet: true });
        }
      }

      toast.add({
        title: "\u4efb\u52a1\u5df2\u79fb\u9664",
        description: "\u5408\u540c\u5ba1\u67e5\u4efb\u52a1\u5df2\u4ece\u5217\u8868\u4e2d\u5220\u9664\u3002",
        color: "success",
      });
    } catch (error) {
      toast.add({
        title: "\u79fb\u9664\u4efb\u52a1\u5931\u8d25",
        description: String(error),
        color: "error",
      });
      throw error;
    } finally {
      deletingJobIds.value = deletingJobIds.value.filter((id) => id !== jobId);
    }
  }

  function selectJob(jobId: string) {
    activeJobId.value = jobId;
    activeTab.value = "results";
    void fetchJobDetail(jobId);
  }

  function downloadExport() {
    if (!detail.value?.export.url || !detail.value.export.available) {
      return;
    }
    const link = document.createElement("a");
    link.href = `${apiBase.replace(/\/api\/v1$/, "")}${detail.value.export.url}`;
    link.download =
      detail.value.export.filename || `${detail.value.job.review_name}.docx`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }

  return {
    templates,
    jobs,
    activeJobId,
    activeTab,
    detail,
    isLoadingTemplates,
    isLoadingJobs,
    isLoadingDetail,
    isCreatingJob,
    isUploadingTemplate,
    deletingTemplateIds,
    deletingJobIds,
    fetchTemplates,
    fetchJobs,
    fetchJobDetail,
    createReviewJob,
    uploadTemplate,
    deleteTemplate,
    deleteJob,
    selectJob,
    downloadExport,
    stopPolling,
  };
});
