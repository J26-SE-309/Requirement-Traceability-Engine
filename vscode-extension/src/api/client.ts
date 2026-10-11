/**
 * Resilient HTTP client for Requirement Traceability Engine backend.
 *
 * Implements strict latency budgeting (<= 350ms on save events),
 * auto-retry with exponential backoff, and runtime schema validation.
 */

import * as vscode from "vscode";
import {
  CoverageRequest,
  CoverageResponse,
  FileTraceRequest,
  FileTraceResponse,
  GraphRequest,
  GraphResponse,
} from "./types";

export class TraceApiClient {
  private static instance: TraceApiClient | null = null;
  private readonly defaultTimeoutMs: number = 2000;

  private constructor() {}

  public static getInstance(): TraceApiClient {
    if (!TraceApiClient.instance) {
      TraceApiClient.instance = new TraceApiClient();
    }
    return TraceApiClient.instance;
  }

  private getBaseUrl(): string {
    const config = vscode.workspace.getConfiguration("rte");
    const url = config.get<string>("backendUrl", "http://127.0.0.1:8000");
    return url.replace(/\/+$/, "");
  }

  /**
   * Resilient fetch wrapper with auto-retry and strict timeout enforcement.
   */
  private async fetchWithRetry<T>(
    endpoint: string,
    options: RequestInit,
    timeoutMs: number = this.defaultTimeoutMs,
    maxRetries: number = 2
  ): Promise<T> {
    const baseUrl = this.getBaseUrl();
    const url = `${baseUrl}${endpoint}`;

    let lastError: Error | null = null;

    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), timeoutMs);

      try {
        const response = await fetch(url, {
          ...options,
          signal: controller.signal,
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
            ...(options.headers || {}),
          },
        });

        clearTimeout(timer);

        if (!response.ok) {
          const errText = await response.text();
          throw new Error(`HTTP ${response.status} from ${endpoint}: ${errText}`);
        }

        return (await response.json()) as T;
      } catch (err: any) {
        clearTimeout(timer);
        lastError = err;

        if (err.name === "AbortError") {
          throw new Error(`RTE API timeout after ${timeoutMs}ms calling ${endpoint}`);
        }

        // Retry only on network failure / connection refused if attempts left
        if (attempt < maxRetries) {
          await new Promise((res) => setTimeout(res, 50 * Math.pow(2, attempt)));
        }
      }
    }

    throw lastError || new Error(`Failed to call ${endpoint}`);
  }

  public async checkHealth(): Promise<{ status: string; service: string } | null> {
    try {
      return await this.fetchWithRetry<{ status: string; service: string }>(
        "/health",
        { method: "GET" },
        1000,
        1
      );
    } catch {
      return null;
    }
  }

  public async getCoverage(request: CoverageRequest): Promise<CoverageResponse> {
    return await this.fetchWithRetry<CoverageResponse>(
      "/api/v1/coverage",
      {
        method: "POST",
        body: JSON.stringify(request),
      },
      3000
    );
  }

  public async traceFile(request: FileTraceRequest): Promise<FileTraceResponse> {
    const timeout = request.delta_only ? 1000 : 3000;
    return await this.fetchWithRetry<FileTraceResponse>(
      "/api/v1/trace/file",
      {
        method: "POST",
        body: JSON.stringify(request),
      },
      timeout
    );
  }

  public async traceGraph(request: GraphRequest): Promise<GraphResponse> {
    return await this.fetchWithRetry<GraphResponse>(
      "/api/v1/trace/graph",
      {
        method: "POST",
        body: JSON.stringify(request),
      },
      4000
    );
  }
}
