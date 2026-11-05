/** Shared types describing a generated evaluation/RL dataset row. */

export interface Message {
  role?: string;
  content?: unknown;
  [key: string]: unknown;
}

export interface DatasetItem {
  prompt?: string | Message[];
  completion?: string | Message[];
  messages?: Message[];
  solution?: string;
  test_cases?: TestCase[];
  metadata?: Record<string, unknown>;
  _viewer?: { index: number; line: number };
  [key: string]: unknown;
}

export interface TestCase {
  name?: string;
  input?: string;
  expected_output?: string;
  test_code?: string;
  [key: string]: unknown;
}

export interface DatasetResponse {
  source: string;
  path: string;
  count: number;
  errors: { line: number; message: string }[];
  items: DatasetItem[];
}
