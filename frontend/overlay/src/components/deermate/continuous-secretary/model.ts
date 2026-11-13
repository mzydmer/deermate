export type RecordView = {
  id: string;
  kind: string;
  state: string;
  revision: number;
  updated_at: number;
  data: Record<string, unknown>;
};
export type Page = { items: RecordView[] };
export type Config = {
  config: RecordView;
  module_available: boolean;
  interactive_available?: boolean;
  github_configured: boolean;
  reserved?: { model: number; native: number };
  budget_day?: string;
};
export type Router = { session: RecordView; items: RecordView[] };
export const str = (v: RecordView, k: string) =>
  typeof v.data[k] === "string" ? v.data[k] : "";
