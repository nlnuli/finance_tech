export type ToolEventMessage = {
  id: number;
  role: "tool";
  event: "start" | "result";
  tool: string;
  content: string;
};

type ToolEventProps = {
  message: ToolEventMessage;
};

export function ToolEvent({ message }: ToolEventProps) {
  const title =
    message.event === "start"
      ? `Tool start: ${message.tool}`
      : `Tool result: ${message.tool}`;

  return (
    <details className="tool-event">
      <summary>{title}</summary>
      <pre>{message.content || "..."}</pre>
    </details>
  );
}
