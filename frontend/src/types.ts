export type DatasetStatus = "queued" | "analyzing" | "ready" | "failed";
export type ReviewStatus = "pending" | "accepted" | "rejected";
export type Action = "set_value" | "drop_row" | "flag";
export type Source = "rule" | "ai";
export type IssueKind =
  | "missing_value"
  | "exact_duplicate"
  | "near_duplicate"
  | "inconsistent_format"
  | "inconsistent_category"
  | "invalid_value"
  | "outlier"
  | "suspicious_record";

export interface DatasetSummary {
  id: string;
  filename: string;
  created_at: string;
  status: DatasetStatus;
  progress: string | null;
  error: string | null;
  row_count: number;
}

export interface ColumnProfile {
  name: string;
  inferred_type: string;
  non_null_count: number;
  null_count: number;
  null_ratio: number;
  distinct_count: number;
  type_confidence: number;
  sample_values: string[];
  top_values: [string, number][];
  numeric_summary: Record<"min" | "max" | "mean" | "median", number> | null;
}

export interface DatasetDetail extends DatasetSummary {
  columns: string[];
  profile: ColumnProfile[];
  warnings: string[];
  ai_model: string | null;
  delimiter: string | null;
  encoding: string | null;
}

export interface Suggestion {
  id: string;
  kind: IssueKind;
  action: Action;
  row_index: number;
  column: string | null;
  current_value: string | null;
  proposed_value: string | null;
  final_value: string | null;
  related_row_index: number | null;
  reason: string;
  confidence: number;
  source: Source;
  group_key: string;
  status: ReviewStatus;
}

export interface RowsPage {
  columns: string[];
  total: number;
  offset: number;
  rows: { index: number; values: string[] }[];
}

export interface Health {
  status: string;
  ai_enabled: boolean;
}
