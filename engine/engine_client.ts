export type AskPayload = {
  query: string;
  scope?: Record<string, unknown>;
  mode?: "auto" | "knowledge" | "experience";
  viewer_role?: "student" | "admin";
  context?: Record<string, unknown>;
};

export class EngineClient {
  private baseUrl: string;
  private clientId?: string;
  private clientToken?: string;

  constructor(baseUrl: string, clientId?: string, clientToken?: string) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.clientId = clientId;
    this.clientToken = clientToken;
  }

  async ingestMessage(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (this.clientId && this.clientToken) {
      headers["X-CLIENT-ID"] = this.clientId;
      headers["X-CLIENT-TOKEN"] = this.clientToken;
    }
    const response = await fetch(`${this.baseUrl}/api/ingest/message`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    });
    return response.json();
  }

  async ask(payload: AskPayload): Promise<Record<string, unknown>> {
    const response = await fetch(`${this.baseUrl}/api/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return response.json();
  }
}
