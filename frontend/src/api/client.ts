/**
 * AgniNetra AI — Full-featured Typed API Client.
 * Communicates with all FastAPI v1 endpoints with robust error handling and query serialization.
 */

import type {
  AlertCreate,
  AlertListResponse,
  AlertRead,
  AlertSeverity,
  AlertStatus,
  AnalyticsSummary,
  FacilityListResponse,
  FeedbackCreate,
  FeedbackListResponse,
  FeedbackRead,
  FIRMSIngestRequest,
  FIRMSIngestResponse,
  HotspotDetail,
  HotspotGeoJSONFeatureCollection,
  HotspotListResponse,
  IngestionRun,
  ModelMetrics,
  PredictionListResponse,
  PredictResponse,
  SystemStatus,
} from "../types";

const API_BASE = "/api/v1";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function buildQuery(params?: Record<string, unknown>): string {
  if (!params) return "";
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      query.append(key, String(value));
    }
  }
  const qs = query.toString();
  return qs ? `?${qs}` : "";
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
    ...options,
  });

  if (!response.ok) {
    let code = `HTTP_${response.status}`;
    let message = response.statusText;
    let details: unknown = null;
    try {
      const body = await response.json();
      code = body?.error?.code ?? body?.code ?? code;
      message = body?.detail ?? body?.error?.message ?? body?.message ?? message;
      details = body?.error?.details ?? body;
    } catch {
      /* response body is not JSON */
    }
    throw new ApiError(response.status, code, message, details);
  }

  return response.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "POST",
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "PATCH",
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
  delete: <T>(path: string) =>
    request<T>(path, {
      method: "DELETE",
    }),
};

/** Hotspots API */
export const hotspotsApi = {
  list: (params?: {
    page?: number;
    per_page?: number;
    min_frp?: number;
    satellite?: string;
    start_date?: string;
    end_date?: string;
    fire_class?: string;
    bbox?: string;
    format?: "json" | "geojson";
  }) => api.get<HotspotListResponse>(`/hotspots${buildQuery(params)}`),

  listGeoJSON: (params?: {
    page?: number;
    per_page?: number;
    min_frp?: number;
    satellite?: string;
    start_date?: string;
    end_date?: string;
    fire_class?: string;
    bbox?: string;
  }) =>
    api.get<HotspotGeoJSONFeatureCollection>(
      `/hotspots${buildQuery({ ...params, format: "geojson" })}`,
    ),

  get: (id: string) => api.get<HotspotDetail>(`/hotspots/${id}`),
};

/** Facilities API */
export const facilitiesApi = {
  list: (params?: {
    facility_type?: string;
    search?: string;
    limit?: number;
    offset?: number;
    format?: "json" | "geojson";
  }) => api.get<FacilityListResponse>(`/facilities${buildQuery(params)}`),
};

/** Predictions API */
export const predictionsApi = {
  list: (params?: {
    page?: number;
    per_page?: number;
    predicted_class?: string;
    min_confidence?: number;
    hotspot_id?: string;
  }) => api.get<PredictionListResponse>(`/predictions${buildQuery(params)}`),

  predict: (hotspotId: string) =>
    api.post<PredictResponse>(`/predict/${hotspotId}`),
};

/** Alerts API */
export const alertsApi = {
  list: (params?: {
    page?: number;
    per_page?: number;
    status?: AlertStatus;
    severity?: AlertSeverity;
  }) => api.get<AlertListResponse>(`/alerts${buildQuery(params)}`),

  create: (payload: AlertCreate) => api.post<AlertRead>("/alerts", payload),

  updateStatus: (id: string, status: AlertStatus) =>
    api.patch<AlertRead>(`/alerts/${id}/status?status=${status}`),
};

/** Analytics API */
export const analyticsApi = {
  summary: () => api.get<AnalyticsSummary>("/analytics/summary"),
};

/** Feedback API */
export const feedbackApi = {
  create: (payload: FeedbackCreate) =>
    api.post<FeedbackRead>("/feedback", payload),

  list: (params?: {
    hotspot_id?: string;
    prediction_id?: string;
    verified_class?: string;
    label_source?: string;
    limit?: number;
    offset?: number;
  }) => api.get<FeedbackListResponse>(`/feedback${buildQuery(params)}`),
};

/** Model Metrics API */
export const modelApi = {
  metrics: () => api.get<ModelMetrics>("/model/metrics"),
};

/** System Status API */
export const systemApi = {
  status: () => api.get<SystemStatus>("/system/status"),
};

/** Ingestion API */
export const ingestionApi = {
  trigger: (payload: FIRMSIngestRequest) =>
    api.post<FIRMSIngestResponse>("/ingestion/firms", payload),

  runs: (params?: { status?: string; limit?: number; offset?: number }) =>
    api.get<IngestionRun[]>(`/ingestion/runs${buildQuery(params)}`),
};
