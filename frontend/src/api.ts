export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export type HealthResponse = {
  status: string;
};

export type AuthUser = {
  id: string;
  email: string;
  display_name: string | null;
  created_at: string;
  updated_at: string | null;
};

export type AuthResponse = {
  access_token: string;
  token_type: "bearer";
  user: AuthUser;
};

export type Thread = {
  id: string;
  user_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
};

export type ApiMessage = {
  id: number;
  thread_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

export type UploadedFile = {
  id: number;
  user_id: string;
  assistant_id: string;
  original_name: string;
  saved_name: string;
  file_path: string;
  content_type: string | null;
  size_bytes: number;
  status: "processing" | "ready" | "failed";
  page_count: number | null;
  chunk_count: number;
  artifact_dir: string | null;
  processing_error: string | null;
  created_at: string;
  updated_at: string | null;
};

export type FileChunk = {
  content: string;
  metadata: Record<string, unknown>;
};

export type ProcessingSummary = {
  status: "ready";
  page_count: number;
  chunk_count: number;
  text_block_count: number;
  table_count: number;
  physical_table_count: number;
  logical_table_count: number;
  stitched_table_count: number;
  form_field_count: number;
  fusion_warning_count: number;
  duration_seconds: number;
  ocr_processor_id: string | null;
  form_processor_id: string | null;
  artifacts: Record<string, string>;
};

export type FileUploadResponse = {
  file: UploadedFile;
  chunks: FileChunk[];
  processing_summary: ProcessingSummary;
};

export type UploadFileOptions = {
  onProgress?: (percent: number) => void;
  onUploadComplete?: () => void;
};

export type ToolInfo = {
  type: string;
  name: string;
  description: string;
  args_schema: Record<string, unknown>;
  source: "local_mcp" | "external_mcp";
  server_name: string;
  transport: "stdio" | "http";
};

const AUTH_TOKEN_KEY = "finance_tech_auth_token";
const AUTH_USER_KEY = "finance_tech_auth_user";

export function getAuthToken(): string | null {
  return localStorage.getItem(AUTH_TOKEN_KEY);
}

export function getStoredUser(): AuthUser | null {
  const rawUser = localStorage.getItem(AUTH_USER_KEY);
  if (!rawUser) return null;
  try {
    return JSON.parse(rawUser) as AuthUser;
  } catch {
    return null;
  }
}

export function storeAuthSession(response: AuthResponse): void {
  localStorage.setItem(AUTH_TOKEN_KEY, response.access_token);
  localStorage.setItem(AUTH_USER_KEY, JSON.stringify(response.user));
}

export function clearAuthSession(): void {
  localStorage.removeItem(AUTH_TOKEN_KEY);
  localStorage.removeItem(AUTH_USER_KEY);
  window.dispatchEvent(new Event("finance-tech-auth-cleared"));
}

function authHeaders(): HeadersInit {
  const token = getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function apiFetch(path: string, options: RequestInit = {}): Promise<Response> {
  const headers = new Headers(options.headers);
  const token = getAuthToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  return fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  });
}

async function responseErrorMessage(
  response: Response,
  fallback: string,
): Promise<string> {
  if (response.status === 401) {
    clearAuthSession();
  }
  try {
    const body = await response.json();
    if (body && typeof body === "object" && "detail" in body) {
      return translateApiError(String(body.detail));
    }
  } catch {
    // Ignore malformed error payloads.
  }
  return `${fallback}: ${response.status}`;
}

function translateApiError(message: string): string {
  const translations: Record<string, string> = {
    "Email already registered": "该邮箱已注册",
    "Invalid email or password": "邮箱或密码错误",
    "Invalid email": "邮箱格式不正确",
    "Not authenticated": "请先登录",
    "Invalid token": "登录已过期，请重新登录",
  };
  return translations[message] ?? message;
}

export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/health`);

  if (!response.ok) {
    throw new Error(`Health check failed: ${response.status}`);
  }

  return response.json();
}

export async function registerUser(
  email: string,
  password: string,
  displayName?: string,
): Promise<AuthResponse> {
  const response = await fetch(`${API_BASE_URL}/api/auth/register`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      email,
      password,
      display_name: displayName || null,
    }),
  });

  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, "注册失败"));
  }

  return response.json();
}

export async function loginUser(
  email: string,
  password: string,
): Promise<AuthResponse> {
  const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ email, password }),
  });

  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, "登录失败"));
  }

  return response.json();
}

export async function getMe(): Promise<AuthUser> {
  const response = await apiFetch("/api/auth/me");

  if (!response.ok) {
    throw new Error(await responseErrorMessage(response, "Load user failed"));
  }

  return response.json();
}

export async function getThreads(): Promise<Thread[]> {
  const response = await apiFetch("/api/threads");

  if (!response.ok) {
    throw new Error(`Load threads failed: ${response.status}`);
  }

  return response.json();
}

export async function getThreadMessages(threadId: string): Promise<ApiMessage[]> {
  const response = await apiFetch(`/api/threads/${threadId}/messages`);

  if (!response.ok) {
    throw new Error(`Load messages failed: ${response.status}`);
  }

  return response.json();
}

function uploadErrorMessage(status: number, response: unknown): string {
  if (response && typeof response === "object" && "detail" in response) {
    const detail = response.detail;
    if (typeof detail === "string") {
      return detail;
    }
    if (detail && typeof detail === "object") {
      const error = "error" in detail ? String(detail.error) : "upload_failed";
      const stage = "stage" in detail ? String(detail.stage) : "upload";
      return `上传失败：${stage} / ${error}`;
    }
  }
  return `上传失败：HTTP ${status}`;
}

export function uploadFile(
  file: File,
  options: UploadFileOptions = {},
): Promise<FileUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", `${API_BASE_URL}/api/files/upload`);
    request.responseType = "json";
    const headers = authHeaders();
    for (const [name, value] of Object.entries(headers)) {
      request.setRequestHeader(name, String(value));
    }

    request.upload.addEventListener("progress", (event) => {
      if (!event.lengthComputable) return;
      const percent = Math.min(100, Math.round((event.loaded / event.total) * 100));
      options.onProgress?.(percent);
    });
    request.upload.addEventListener("load", () => {
      options.onProgress?.(100);
      options.onUploadComplete?.();
    });
    request.addEventListener("load", () => {
      if (request.status >= 200 && request.status < 300) {
        resolve(request.response as FileUploadResponse);
        return;
      }
      reject(new Error(uploadErrorMessage(request.status, request.response)));
    });
    request.addEventListener("error", () => {
      reject(new Error("上传失败：无法连接后端服务"));
    });
    request.addEventListener("abort", () => {
      reject(new Error("上传已取消"));
    });
    request.send(formData);
  });
}

export async function getTools(): Promise<ToolInfo[]> {
  const response = await apiFetch("/api/tools");

  if (!response.ok) {
    throw new Error(`Load tools failed: ${response.status}`);
  }

  return response.json();
}
