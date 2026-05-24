export type ChatMessage = {
  id: number;
  role: "assistant" | "user";
  content: string;
};

type MessageListProps = {
  messages: ChatMessage[];
};

export function MessageList({ messages }: MessageListProps) {
  return (
    <div className="messages" aria-live="polite">
      {messages.map((message) => (
        <div className={`message ${message.role}`} key={message.id}>
          <span>{message.role === "assistant" ? "Assistant" : "You"}</span>
          <p>{message.content || "..."}</p>
        </div>
      ))}
    </div>
  );
}
