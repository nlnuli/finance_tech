import { MarkdownMessage } from "./MarkdownMessage";
import { ToolEvent, ToolEventMessage } from "./ToolEvent";

export type ChatMessage = {
  id: number;
  role: "assistant" | "user";
  content: string;
};

export type MessageItem = ChatMessage | ToolEventMessage;

type MessageListProps = {
  messages: MessageItem[];
};

export function MessageList({ messages }: MessageListProps) {
  return (
    <div className="messages" aria-live="polite">
      {messages.map((message) =>
        message.role === "tool" ? (
          <ToolEvent message={message} key={message.id} />
        ) : (
          <div className={`message ${message.role}`} key={message.id}>
            <span>{message.role === "assistant" ? "Assistant" : "You"}</span>
            <MarkdownMessage content={message.content} />
          </div>
        ),
      )}
    </div>
  );
}
