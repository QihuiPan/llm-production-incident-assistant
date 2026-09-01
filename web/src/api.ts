import type { Incident, Investigation } from "./types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(detail.detail ?? "Request failed");
  }
  return response.json() as Promise<T>;
}

export function createIncident(payload: Omit<Incident, "id" | "status">): Promise<Incident> {
  return request("/api/incidents", { method: "POST", body: JSON.stringify(payload) });
}

export function investigateIncident(id: string): Promise<Investigation> {
  return request(`/api/incidents/${id}/investigate`, { method: "POST" });
}

export async function approveTool(id: string): Promise<void> {
  await request(`/api/tool-calls/${id}/approve`, {
    method: "POST",
    body: JSON.stringify({ approved_by: "portfolio-operator" }),
  });
}
