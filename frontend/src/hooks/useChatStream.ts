import { useState } from "react";

import { API_BASE_URL } from "../api";

type StreamEvent = {
  event: string;
  data: Record<string, string>;
};

type SendMessageOptions = {
  message: string;
  threadId?: string;
  ragEnabled?: boolean;
  onMetadata?: (data: Record<string, string>) => void;
  onToken?: (token: string) => void;
  onMessage?: (content: string) => void;
  onError?: (message: string) => void;
  onEnd?: () => void;
};

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

  async function sendMessage(options: SendMessageOptions) {
    setIsLoading(true);

    try {
      const response = await fetch(`${API_BASE_URL}/api/chat/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          message: options.message,
          thread_id: options.threadId,
          rag_enabled: options.ragEnabled ?? false,
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
            options.onToken?.(parsed.data.content ?? "");
          }
          if (parsed.event === "message") {
            options.onMessage?.(parsed.data.content ?? "");
          }
          if (parsed.event === "error") {
            options.onError?.(parsed.data.message ?? "Unknown stream error");
          }
          if (parsed.event === "end") {
            options.onEnd?.();
          }
        }
      }
    } catch (error) {
      options.onError?.(error instanceof Error ? error.message : "Unknown error");
    } finally {
      setIsLoading(false);
    }
  }

  return {
    isLoading,
    sendMessage,
  };
}
