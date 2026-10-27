export type Prediction = {
  scan_id: number;
  predicted_label: string;
  risk_score: number;
  explanation: string;
};

export type User = {
  id: number;
  name: string;
  email: string;
};

export type HealthResult = {
  ok: boolean;
  detail: string;
};

export type SystemHealth = {
  database: HealthResult;
  model: HealthResult;
};

export type ScanSummary = {
  scan_id: number;
  predicted_label: string;
  risk_score: number;
  created_at: string;
  record_kind: "user" | "verification" | "demo" | "legacy";
};

export type ScanDetails = ScanSummary & {
  explanation: string;
};

export type ScanPage = {
  items: ScanSummary[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

export type DashboardSummary = {
  total_scans: number;
  phishing_scans: number;
  safe_scans: number;
  recent_scans: ScanSummary[];
};

export type Evaluation = {
  model_name: string;
  model_version: string;
  dataset_name: string;
  dataset_source: string;
  dataset_license: string;
  trained_at_utc: string;
  dataset_counts: {
    source_rows: number;
    missing_text_rows: number;
    missing_label_rows: number;
    blank_text_rows: number;
    conflicting_duplicate_groups: number;
    conflicting_rows_excluded: number;
    duplicate_rows_collapsed: number;
    usable_unique_rows: number;
  };
  class_counts_after_deduplication: Record<string, number>;
  training_rows: number;
  test_rows: number;
  test_size_fraction: number;
  random_state: number;
  positive_class: string;
  precision: number;
  recall: number;
  f1_score: number;
  false_positive_rate: number;
  confusion_matrix_labels: string[];
  confusion_matrix: number[][];
  false_positive_analysis: {
    false_positives: number;
    true_negatives: number;
    false_positive_rate: number;
    definition: string;
  };
};

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");

async function getCsrfToken(): Promise<string> {
  const result = await request<{ csrf_token: string }>("/api/auth/csrf");
  return result.csrf_token;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    const headers = new Headers(init?.headers);
    headers.set("Accept", "application/json");
    if (init?.method?.toUpperCase() === "POST" && path !== "/api/auth/csrf") {
      headers.set("X-CSRF-Token", await getCsrfToken());
    }
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      credentials: "include",
      headers,
    });
  } catch {
    throw new ApiError(
      "Cannot reach the API. Confirm FastAPI is running at the configured API address.",
    );
  }

  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && !["/api/auth/me", "/api/auth/login", "/api/auth/register"].includes(path)) {
      window.dispatchEvent(new Event("phishshift:unauthorized"));
    }
    const rawDetail =
      typeof body === "object" &&
      body !== null &&
      "detail" in body &&
      body.detail !== undefined
        ? body.detail
        : null;
    const detail = typeof rawDetail === "string"
      ? rawDetail
      : Array.isArray(rawDetail)
        ? rawDetail
            .map((item) =>
              typeof item === "object" && item !== null && "msg" in item && typeof item.msg === "string"
                ? item.msg.replace(/^Value error,\s*/i, "")
                : "One or more fields are invalid.",
            )
            .join(" ")
        : `The API returned HTTP ${response.status}.`;
    throw new ApiError(detail || `The API returned HTTP ${response.status}.`, response.status);
  }
  return body as T;
}

export function registerAccount(input: {
  name: string;
  email: string;
  password: string;
  confirm_password: string;
}): Promise<{ user: User }> {
  return request("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function loginAccount(input: {
  email: string;
  password: string;
}): Promise<{ user: User }> {
  return request("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function getCurrentUser(): Promise<{ user: User; expires_in: number }> {
  return request("/api/auth/me");
}

export function logoutAccount(): Promise<{ status: string }> {
  return request("/api/auth/logout", { method: "POST" });
}

export async function getHealth(path: string): Promise<HealthResult> {
  try {
    const result = await request<{ status: string; detail?: string }>(path);
    return result.status === "ok"
      ? { ok: true, detail: "Connected" }
      : { ok: false, detail: result.detail ?? "The service reported unavailable." };
  } catch (error) {
    return {
      ok: false,
      detail: error instanceof Error ? error.message : "Health check failed.",
    };
  }
}

export async function getSystemHealth(): Promise<SystemHealth> {
  const [database, model] = await Promise.all([
    getHealth("/health/db"),
    getHealth("/health/model"),
  ]);
  return { database, model };
}

export function createPrediction(
  message: string,
  recordKind: "user" | "verification" = "user",
): Promise<Prediction> {
  return request<Prediction>("/api/predict", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, record_kind: recordKind }),
  });
}

export function getScanHistory(
  page = 1,
  pageSize = 10,
  label?: "Safe Email" | "Phishing Email",
  sortBy: "created_at" | "risk_score" = "created_at",
  sortOrder: "asc" | "desc" = "desc",
): Promise<ScanPage> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
    sort_by: sortBy,
    sort_order: sortOrder,
  });
  if (label) params.set("label", label);
  return request<ScanPage>(`/api/scans?${params.toString()}`);
}

export function getDashboardSummary(): Promise<DashboardSummary> {
  return request<DashboardSummary>("/api/dashboard/summary");
}

export function getScanDetails(scanId: number): Promise<ScanDetails> {
  return request<ScanDetails>(`/api/scans/${scanId}`);
}

export function getEvaluation(): Promise<Evaluation> {
  return request<Evaluation>("/api/model/evaluation");
}
