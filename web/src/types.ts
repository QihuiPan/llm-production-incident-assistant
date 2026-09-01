export type Incident = {
  id: string;
  service: string;
  environment: string;
  alert: string;
  window_start: string;
  window_end: string;
  status: string;
};

export type Evidence = {
  id: string;
  source_type: "document" | "tool";
  source: string;
  source_version: string;
  trust_level: "official" | "reviewed" | "unverified";
  excerpt: string;
  score: number;
  metadata: Record<string, unknown>;
};

export type ToolProposal = {
  id: string;
  tool: string;
  arguments: Record<string, unknown>;
  reason: string;
  status: string;
};

export type Investigation = {
  incident_id: string;
  summary: string;
  timeline: Array<{ at: string; event: string; evidence_ids: string[] }>;
  hypotheses: Array<{
    cause: string;
    confidence: number;
    supporting_evidence: string[];
    contradictions: string[];
  }>;
  next_queries: ToolProposal[];
  evidence: Evidence[];
  security_events: string[];
  insufficient_evidence: boolean;
  metrics: {
    retrieval_ms: number;
    composition_ms: number;
    total_ms: number;
    estimated_tokens: number;
    estimated_cost_usd: number;
    config_version: string;
  };
};
