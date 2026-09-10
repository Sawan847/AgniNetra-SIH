/**
 * Shared TypeScript type definitions for AgniNetra AI Platform.
 * Aligned with backend FastAPI v1 schemas and PostGIS models.
 */

/** Health check types */
export interface ServiceStatus {
  name: string;
  status: "healthy" | "unhealthy";
  latency_ms: number | null;
  error: string | null;
}

export interface HealthResponse {
  status: "healthy" | "degraded" | "unhealthy";
  version: string;
  environment: string;
  timestamp: string;
  services: ServiceStatus[];
}

/** Fire Classification Categories (Standardized SIH 6-Class Taxonomy) */
export type FireClass =
  | "accidental_industrial_fire"
  | "persistent_industrial_source"
  | "forest_or_natural_fire"
  | "agricultural_burning"
  | "mining_or_other"
  | "uncertain";

export const FIRE_CLASS_LABELS: Record<FireClass, string> = {
  accidental_industrial_fire: "Accidental Industrial Fire",
  persistent_industrial_source: "Persistent Industrial Thermal / Flare",
  forest_or_natural_fire: "Forest / Natural Fire",
  agricultural_burning: "Agricultural Stubble Burning",
  mining_or_other: "Mining / Other Thermal Source",
  uncertain: "Uncertain / Under Review",
};

export const FIRE_CLASS_COLORS: Record<FireClass, string> = {
  accidental_industrial_fire: "#DC2626", // Red (critical emergency)
  persistent_industrial_source: "#EA580C", // Amber/Orange (monitored industrial)
  forest_or_natural_fire: "#16A34A", // Forest green
  agricultural_burning: "#CA8A04", // Mustard / Goldenrod
  mining_or_other: "#7C3AED", // Violet
  uncertain: "#64748B", // Slate
};

export const FIRE_CLASS_BG_COLORS: Record<FireClass, string> = {
  accidental_industrial_fire: "rgba(220, 38, 38, 0.10)",
  persistent_industrial_source: "rgba(234, 88, 12, 0.10)",
  forest_or_natural_fire: "rgba(22, 163, 74, 0.10)",
  agricultural_burning: "rgba(202, 138, 4, 0.10)",
  mining_or_other: "rgba(124, 58, 237, 0.10)",
  uncertain: "rgba(100, 116, 139, 0.10)",
};

/** Hotspot Models */
export interface Hotspot {
  id: string;
  event_id?: string | null;
  latitude: number;
  longitude: number;
  brightness?: number | null;
  bright_ti4?: number | null;
  bright_ti5?: number | null;
  frp?: number | null;
  confidence?: number | null;
  satellite?: string | null;
  instrument?: string | null;
  acq_date?: string | null;
  acq_time?: string | null;
  daynight?: string | null;
  source?: string | null;
  ingested_at: string;
  predicted_class?: FireClass | null;
  confidence_score?: number | null;
}

export interface HotspotDetail extends Hotspot {
  raw_data?: Record<string, unknown> | null;
  features?: Record<string, unknown> | null;
  predictions?: PredictionRead[];
  alerts?: AlertRead[];
}

export interface HotspotListResponse {
  status: string;
  data: Hotspot[];
  meta: {
    total: number;
    page: number;
    per_page: number;
  };
}

/** GeoJSON types */
export interface GeoJSONGeometryPoint {
  type: "Point";
  coordinates: [number, number]; // [longitude, latitude]
}

export interface HotspotGeoJSONFeature {
  type: "Feature";
  id: string;
  geometry: GeoJSONGeometryPoint;
  properties: Record<string, unknown>;
}

export interface HotspotGeoJSONFeatureCollection {
  type: "FeatureCollection";
  features: HotspotGeoJSONFeature[];
  meta?: Record<string, unknown>;
}

/** Industrial Facility Models */
export interface IndustrialFacility {
  id: string;
  name: string;
  facility_type?: string | null;
  osm_id?: string | null;
  source?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  metadata?: Record<string, unknown> | null;
  created_at: string;
}

export interface FacilityListResponse {
  status: string;
  data: IndustrialFacility[];
  meta: {
    total: number;
    limit: number;
    offset: number;
  };
}

/** Predictions & ML Models */
export interface PredictionRead {
  id: string;
  hotspot_id: string;
  model_version_id?: string | null;
  predicted_class: FireClass;
  confidence_score?: number | null;
  stage1_class?: string | null;
  stage1_probabilities?: Record<string, number> | null;
  stage2_class?: string | null;
  stage2_probabilities?: Record<string, number> | null;
  class_probabilities?: Record<string, number> | null;
  feature_importances?: Record<string, number> | null;
  explanation?: {
    top_factors?: string[];
    primary_driver?: string;
  } | null;
  predicted_at: string;
}

export interface PredictResponse {
  status: string;
  data: PredictionRead;
  alert_created: boolean;
  alert_id?: string | null;
}

export interface PredictionListResponse {
  status: string;
  data: PredictionRead[];
  meta: {
    total: number;
    page: number;
    per_page: number;
  };
}

/** Alert Models */
export type AlertSeverity = "critical" | "high" | "medium" | "low";
export type AlertStatus = "active" | "acknowledged" | "resolved" | "false_positive";

export interface AlertRead {
  id: string;
  hotspot_id: string;
  prediction_id?: string | null;
  severity: AlertSeverity;
  alert_type?: string | null;
  status: AlertStatus;
  description?: string | null;
  metadata?: Record<string, unknown> | null;
  created_at: string;
  resolved_at?: string | null;
}

export interface AlertCreate {
  hotspot_id: string;
  prediction_id?: string | null;
  severity: AlertSeverity;
  alert_type?: string | null;
  status?: AlertStatus;
  description?: string | null;
  metadata?: Record<string, unknown> | null;
}

export interface AlertListResponse {
  status: string;
  data: AlertRead[];
  meta: {
    total: number;
    page: number;
    per_page: number;
  };
}

/** Analytics Summary Models */
export interface AnalyticsSummary {
  status: string;
  total_hotspots: number;
  total_facilities: number;
  total_alerts: number;
  active_alerts: number;
  classification_distribution: Record<string, number>;
  severity_distribution: Record<string, number>;
  avg_frp: number;
  max_frp: number;
  satellite_sensor_distribution: Record<string, number>;
  recent_trend_7d: Array<{ date: string; count: number }>;
}

/** Analyst Feedback Models */
export interface FeedbackCreate {
  hotspot_id?: string | null;
  prediction_id?: string | null;
  suggested_class?: string | null;
  verified_class: FireClass;
  is_correct: boolean;
  reviewer_name: string;
  label_source?: string;
  evidence?: Record<string, unknown> | null;
  notes?: string | null;
}

export interface FeedbackRead extends FeedbackCreate {
  id: string;
  user_id?: string | null;
  created_at: string;
}

export interface FeedbackListResponse {
  status: string;
  data: FeedbackRead[];
  meta: {
    total: number;
    limit: number;
    offset: number;
  };
}

/** Model Metrics Models */
export interface ModelMetrics {
  status: string;
  active_model_name: string;
  algorithm: string;
  version: string;
  evaluation_metrics: {
    accuracy?: number;
    macro_f1?: number;
    weighted_f1?: number;
    macro_precision?: number;
    macro_recall?: number;
    mean_spatial_cv_f1?: number;
    false_alert_rate_industrial_fire?: number;
    confusion_matrix?: number[][] | { labels: string[]; matrix: number[][] };
    per_class_metrics?: Record<string, {
      precision: number;
      recall: number;
      f1: number;
      support: number;
    }>;

    // Emitted by ml.training.train_pipeline's model card. These describe the model
    // that is actually loaded, so the dashboard reports real figures instead of the
    // hardcoded placeholders it used to fall back to.
    abstain_rate?: number;
    macro_f1_on_confident_subset?: number;
    n_features?: number;
    classes?: string[];
    data_provenance?: string;
    per_class?: Record<string, Record<string, number>>;
    label_coverage?: {
      coverage?: number;
      labelled?: number;
      total_detections?: number;
      unlabelled_excluded?: number;
      class_counts?: Record<string, number>;
    };
    feature_ablation?: {
      spatial_cv_macro_f1_all_features?: number;
      spatial_cv_macro_f1_ablated?: number;
      delta?: number;
      withheld_features?: string[];
    };
    holdout_class_coverage?: {
      classes_in_holdout?: string[];
      classes_missing_from_holdout?: string[];
      warning?: string;
    };
    label_circularity_note?: string;
    known_limitations?: string[];
  };
  feature_importances: Record<string, number>;
  model_card?: {
    model_name?: string;
    version?: string;
    description?: string;
    algorithm?: string;
    features_count?: number;
    target_classes?: string[];
    validation_strategy?: string;
    timestamp?: string;
    uncertainty_threshold?: number;
    data_leakage_safeguards?: string[];
    algorithm_comparison?: Record<string, {
      spatial_cv_macro_f1: number;
      holdout_accuracy: number;
      holdout_macro_f1: number;
      holdout_weighted_f1: number;
      false_alert_rate: number;
    }>;
  } | null;
}

/** System Status Models */
export interface SystemStatus {
  status: "healthy" | "degraded" | "unhealthy";
  version: string;
  environment: string;
  timestamp: string;
  database_connected: boolean;
  gee_connected: boolean;
  firms_configured: boolean;
  total_records: Record<string, number>;
  services: Array<{
    name: string;
    status: string;
    backend?: string;
  }>;
}

/** Ingestion Models */
export interface IngestionRun {
  id: string;
  source: string;
  status: "running" | "completed" | "failed";
  records_fetched: number;
  records_inserted: number;
  records_skipped: number;
  error_message?: string | null;
  started_at: string;
  completed_at?: string | null;
}

export interface FIRMSIngestRequest {
  bbox: [number, number, number, number]; // [min_lon, min_lat, max_lon, max_lat]
  start_date: string;
  end_date?: string | null;
  sources?: string[];
}

export interface FIRMSIngestResponse {
  status: string;
  message: string;
  run_id: string;
  data?: IngestionRun | null;
}

/** UI Navigation */
export interface NavItem {
  label: string;
  path: string;
  badge?: number | string;
}
