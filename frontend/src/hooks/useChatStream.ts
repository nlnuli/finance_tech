import { useRef, useState } from "react";

import { API_BASE_URL, getAuthToken } from "../api";

type StreamEvent = {
  event: string;
  data: Record<string, unknown>;
};

type SendMessageOptions = {
  message: string;
  threadId?: string;
  ragEnabled?: boolean;
  mode?: string;
  onMetadata?: (data: Record<string, unknown>) => void;
  onToken?: (token: string) => void;
  onMessage?: (content: string) => void;
  onPlan?: (data: Record<string, unknown>) => void;
  onStepStart?: (data: Record<string, unknown>) => void;
  onStepResult?: (data: Record<string, unknown>) => void;
  onToolStart?: (data: Record<string, unknown>) => void;
  onToolResult?: (data: Record<string, unknown>) => void;
  onError?: (message: string) => void;
  onEnd?: () => void;
};

export type StreamStatus = "idle" | "inflight" | "error" | "done";

function toText(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function parseSseEvent(rawEvent: string): StreamEvent | null {
  const lines = rawEvent.split("\n");
  const eventLine = lines.find((line) => line.startsWith("event:"));
  const dataLines = lines.filter((line) => line.startsWith("data:"));

  if (!eventLine || dataLines.length === 0) {
    return null;
  }

  const event = eventLine.replace(/^event:\s*/, "");
  const dataText = dataLines
    .map((line) => line.replace(/^data:\s*/, ""))
    .join("\n");

  return {
    event,
    data: JSON.parse(dataText),
  };
}

export function useChatStream() {
  const [isLoading, setIsLoading] = useState(false);
  const [status, setStatus] = useState<StreamStatus>("idle");
  const [errorMessage, setErrorMessage] = useState("");
  const abortControllerRef = useRef<AbortController | null>(null);

  function stop() {
    abortControllerRef.current?.abort();
  }

  async function sendMessage(options: SendMessageOptions) {
    abortControllerRef.current?.abort();

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    setIsLoading(true);
    setStatus("inflight");
    setErrorMessage("");

    try {
      const response = await fetch(`${API_BASE_URL}/api/chat/stream`, {
        method: "POST",
        headers: {
          ...(getAuthToken()
            ? { Authorization: `Bearer ${getAuthToken()}` }
            : {}),
          "Content-Type": "application/json",
        },
        signal: abortController.signal,
        body: JSON.stringify({
          message: options.message,
          thread_id: options.threadId,
          rag_enabled: options.ragEnabled ?? false,
          mode: options.mode ?? "react",
        }),
      });

      if (!response.ok || !response.body) {
        throw new Error(`Stream request failed: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";

        for (const rawEvent of events) {
          const parsed = parseSseEvent(rawEvent);
          if (!parsed) continue;

          if (parsed.event === "metadata") {
            options.onMetadata?.(parsed.data);
          }
          if (parsed.event === "token") {
            options.onToken?.(toText(parsed.data.content));
          }
          if (parsed.event === "message") {
            options.onMessage?.(toText(parsed.data.content));
          }
          if (parsed.event === "plan") {
            options.onPlan?.(parsed.data);
          }
          if (parsed.event === "step_start") {
            options.onStepStart?.(parsed.data);
          }
          if (parsed.event === "step_result") {
            options.onStepResult?.(parsed.data);
          }
          if (parsed.event === "tool_start") {
            options.onToolStart?.(parsed.data);
          }
          if (parsed.event === "tool_result") {
            options.onToolResult?.(parsed.data);
          }
          if (parsed.event === "error") {
            const message = toText(parsed.data.message) || "Unknown stream error";
            setStatus("error");
            setErrorMessage(message);
            options.onError?.(message);
          }
          if (parsed.event === "end") {
            setStatus((current) => (current === "error" ? "error" : "done"));
            options.onEnd?.();
          }
        }
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        setStatus("done");
        options.onEnd?.();
        return;
      }

      const message = error instanceof Error ? error.message : "Unknown error";
      setStatus("error");
      setErrorMessage(message);
      options.onError?.(message);
    } finally {
      if (abortControllerRef.current === abortController) {
        abortControllerRef.current = null;
      }
      setStatus((current) => (current === "inflight" ? "done" : current));
      setIsLoading(false);
    }
  }

  return {
    errorMessage,
    isLoading,
    sendMessage,
    status,
    stop,
  };
}
