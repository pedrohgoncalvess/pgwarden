import { env } from "@/lib/env";

const API_BASE_URL = env.VITE_API_BASE_URL ?? "http://localhost:8080/v1";
const REQUEST_TIMEOUT_MS = 10_000;
const BASE_HEADERS = {
  Accept: "application/json",
} as const;
const normalizedApiBaseUrl = API_BASE_URL.endsWith("/") ? API_BASE_URL : `${API_BASE_URL}/`;

type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

type HttpClientOptions = {
  method?: HttpMethod;
  headers?: HeadersInit;
  body?: unknown;
  timeoutMs?: number;
};

async function parseResponse<TResponse>(response: Response): Promise<TResponse> {
  if (!response.ok) {
    const errorBody = await response.text().catch(() => "");
    throw new Error(
      `Request failed (${response.status} ${response.statusText})${errorBody ? `: ${errorBody}` : ""}`
    );
  }

  if (response.status === 204) {
    return undefined as TResponse;
  }

  const textBody = await response.text();
  if (!textBody) {
    return undefined as TResponse;
  }

  return JSON.parse(textBody) as TResponse;
}

export async function httpClient<TResponse = unknown>(
  endpoint: string,
  options: HttpClientOptions = {}
): Promise<TResponse> {
  const { method = "GET", headers, body, timeoutMs = REQUEST_TIMEOUT_MS } = options;
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    const requestHeaders = new Headers(BASE_HEADERS);
    if (body !== undefined) {
      requestHeaders.set("Content-Type", "application/json");
    }
    if (headers) {
      const customHeaders = new Headers(headers);
      customHeaders.forEach((value, key) => requestHeaders.set(key, value));
    }

    const response = await fetch(new URL(endpoint, normalizedApiBaseUrl), {
      method,
      headers: requestHeaders,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });

    return await parseResponse<TResponse>(response);
  } finally {
    window.clearTimeout(timeoutId);
  }
}
