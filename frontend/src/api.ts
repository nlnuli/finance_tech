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
