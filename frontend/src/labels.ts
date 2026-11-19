import type { IssueKind, Suggestion } from "./types";

export const KIND_LABELS: Record<IssueKind, string> = {
  missing_value: "Missing values",
  inconsistent_format: "Inconsistent formatting",
  inconsistent_category: "Spelling variants",
  invalid_value: "Invalid values",
  outlier: "Unusual values",
  exact_duplicate: "Duplicate rows",
  near_duplicate: "Possible duplicates",
  suspicious_record: "Suspicious records",
};

export const KIND_ORDER: IssueKind[] = [
  "exact_duplicate",
  "near_duplicate",
  "inconsistent_category",
  "inconsistent_format",
  "invalid_value",
  "missing_value",
  "outlier",
  "suspicious_record",
];

/** Turns a group key such as "date_format:signup_date:MM/DD/YYYY" into a title. */
export function groupTitle(groupKey: string, sample: Suggestion): string {
  const [type = "", column = "", ...rest] = groupKey.split(":");
  const detail = rest.join(":");
  switch (type) {
    case "null_token":
      return `"${sample.current_value?.trim()}" used for empty ${column}`;
    case "missing":
      return `Empty ${column}`;
    case "whitespace":
      return `Extra spaces in ${column}`;
    case "email_case":
      return `Capital letters in ${column}`;
    case "email_repair":
      return `Repairable emails in ${column}`;
    case "email_invalid":
      return `Invalid emails in ${column}`;
    case "phone_format":
      return `Phone numbers to convert to E.164`;
    case "phone_invalid":
      return `Invalid phone numbers in ${column}`;
    case "date_format":
      return `${column} written as ${detail}`;
    case "date_invalid":
      return `Unreadable dates in ${column}`;
    case "date_range":
      return `Implausible years in ${column}`;
    case "number_format":
      return `Formatted numbers in ${column}`;
    case "number_invalid":
      return `Non-numeric ${column}`;
    case "boolean_format":
      return `Yes/no spelling in ${column}`;
    case "category":
      return `"${detail}" in ${column}`;
    case "outlier":
      return `Unusual ${column}`;
    case "negative":
      return `Negative ${column}`;
    case "exact_duplicate":
      return "Rows identical to an earlier row";
    case "near_duplicate":
      return "Rows that look like an earlier row";
    case "suspicious":
      return column === "row" ? "Records that contradict themselves" : `Suspicious ${column}`;
    default:
      return groupKey;
  }
}

export function rowLabel(index: number): string {
  return `Row ${(index + 1).toLocaleString()}`;
}
