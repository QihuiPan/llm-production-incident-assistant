import type { Dashboard, Incident, Investigation } from "./types";

const API_URL = import.meta.env.VITE_API_URL ?? (import.meta.env.DEV ? "http://localhost:8000" : "");
let apiKey = sessionStorage.getItem("incident-assistant-api-key") ?? "";

export function configureApiKey(value: string): void {
  apiKey = value.trim();
  if (apiKey) sessionStorage.setItem("incident-assistant-api-key", apiKey);
  else sessionStorage.removeItem("incident-assistant-api-key");
}

export function getConfiguredApiKey(): string {
  return apiKey;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(apiKey ? { Authorization: `Bearer ${apiKey}` } : {}),
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }));
    const detail = Array.isArray(payload.detail)
      ? payload.detail.map((item: { msg?: string }) => item.msg ?? "Invalid input").join("; ")
      : payload.detail;
    if (response.status === 429) {
      const retryAfter = response.headers.get("Retry-After");
      throw new Error(
        `${detail ?? "Public demo rate limit reached"}. Try again${retryAfter ? ` in ${retryAfter} seconds` : " later"}.`,
      );
    }
    throw new Error(detail ?? "Request failed");
  }
  return response.json() as Promise<T>;
}

export function createIncident(payload: Omit<Incident, "id" | "status">): Promise<Incident> {
  return request("/api/incidents", { method: "POST", body: JSON.stringify(payload) });
}

export function investigateIncident(id: string): Promise<Investigation> {
  return request(`/api/incidents/${id}/investigate`, { method: "POST" });
}

export function investigateDemo(
  payload: Omit<Incident, "id" | "status">,
): Promise<Investigation> {
  return request("/api/demo/investigate", { method: "POST", body: JSON.stringify(payload) });
}

export async function approveTool(id: string): Promise<void> {
  await request(`/api/tool-calls/${id}/approve`, {
    method: "POST",
    body: JSON.stringify({ approved_by: "portfolio-operator" }),
  });
}

export function getDashboard(): Promise<Dashboard> {
  return request("/api/dashboard");
}

export async function submitFeedback(
  incidentId: string,
  payload: {
    correctness: number;
    citation_quality: number;
    helpfulness: number;
    label: string;
    correction: string | null;
  },
): Promise<void> {
  await request(`/api/incidents/${incidentId}/feedback`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function downloadPostmortem(incidentId: string): Promise<void> {
  const response = await fetch(`${API_URL}/api/incidents/${incidentId}/postmortem`, {
    headers: apiKey ? { Authorization: `Bearer ${apiKey}` } : {},
  });
  if (!response.ok) throw new Error("Postmortem export failed");
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${incidentId}-postmortem.md`;
  anchor.click();
  URL.revokeObjectURL(url);
}
