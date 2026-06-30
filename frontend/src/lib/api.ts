export type SourceType =
  | "json"
  | "pdf"
  | "html"
  | "markdown"
  | "chatgpt"
  | "meta";

export type Source = {
  id: string;
  source_type: string;
  original_filename: string | null;
  import_status: string;
  file_size_bytes: number | null;
  imported_at: string | null;
  observation_count: number;
};

export type Observation = {
  id: string;
  content: string;
  speaker: string | null;
  observed_at: string | null;
  confidence: number;
  source_id: string | null;
};

export type Job = {
  id: string;
  job_type: string;
  status: string;
  attempts: number;
  error: string | null;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
};

export type DashboardSummary = {
  source_count: number;
  observation_count: number;
  pending_job_count: number;
  recent_sources: Source[];
};

export type UploadResult = {
  source_id: string;
  job_id: string;
  status: string;
};

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }
  const response = await fetch(`/api${path}`, {
    ...init,
    headers,
    credentials: "include"
  });
  if (!response.ok) {
    const detail = await response
      .json()
      .then((body: { detail?: string }) => body.detail)
      .catch(() => response.statusText);
    throw new Error(detail || response.statusText);
  }
  return (await response.json()) as T;
}

export const api = {
  me: () => request<{ user_id: string }>("/auth/me"),
  login: (password: string) =>
    request<{ user_id: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ password })
    }),
  logout: () => request<{ status: string }>("/auth/logout", { method: "POST" }),
  dashboard: () => request<DashboardSummary>("/dashboard/summary"),
  sources: () => request<Source[]>("/sources"),
  source: (sourceId: string) => request<Source>(`/sources/${sourceId}`),
  observations: (params: URLSearchParams = new URLSearchParams()) => {
    const query = params.toString();
    return request<Observation[]>(`/observations${query ? `?${query}` : ""}`);
  },
  job: (jobId: string) => request<Job>(`/jobs/${jobId}`),
  uploadSource: (sourceType: SourceType, file: File) => {
    const formData = new FormData();
    formData.set("source_type", sourceType);
    formData.set("file", file);
    return request<UploadResult>("/sources/upload", {
      method: "POST",
      body: formData
    });
  }
};

export function formatDate(value: string | null): string {
  if (!value) {
    return "unknown";
  }
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

export function formatBytes(value: number | null): string {
  if (value === null) {
    return "unknown";
  }
  if (value < 1024) {
    return `${value} B`;
  }
  const kb = value / 1024;
  if (kb < 1024) {
    return `${kb.toFixed(1)} KB`;
  }
  return `${(kb / 1024).toFixed(1)} MB`;
}
