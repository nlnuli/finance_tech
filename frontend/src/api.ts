export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export type HealthResponse = {
  status: string;
};

export type Thread = {
  id: string;
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
  assistant_id: string;
  original_name: string;
  saved_name: string;
  file_path: string;
  content_type: string | null;
  size_bytes: number;
  created_at: string;
};

export type FileChunk = {
  content: string;
  metadata: Record<string, string | number>;
};

export type FileUploadResponse = {
  file: UploadedFile;
  chunks: FileChunk[];
};

export type ToolInfo = {
  type: string;
  name: string;
  description: string;
  args_schema: Record<string, unknown>;
};

export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/health`);

  if (!response.ok) {
    throw new Error(`Health check failed: ${response.status}`);
  }

  return response.json();
}

export async function getThreads(): Promise<Thread[]> {
  const response = await fetch(`${API_BASE_URL}/api/threads`);

  if (!response.ok) {
    throw new Error(`Load threads failed: ${response.status}`);
  }

  return response.json();
}

export async function getThreadMessages(threadId: string): Promise<ApiMessage[]> {
  const response = await fetch(`${API_BASE_URL}/api/threads/${threadId}/messages`);

  if (!response.ok) {
    throw new Error(`Load messages failed: ${response.status}`);
  }

  return response.json();
}

export async function uploadFile(
  file: File,
  assistantId = "default",
): Promise<FileUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("assistant_id", assistantId);

  const response = await fetch(`${API_BASE_URL}/api/files/upload`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`Upload file failed: ${response.status}`);
  }

  return response.json();
}

export async function getTools(): Promise<ToolInfo[]> {
  const response = await fetch(`${API_BASE_URL}/api/tools`);

  if (!response.ok) {
    throw new Error(`Load tools failed: ${response.status}`);
  }

  return response.json();
}
