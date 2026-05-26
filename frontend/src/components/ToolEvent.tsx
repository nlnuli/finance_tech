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
    <div className="tool-event">
      <span>{title}</span>
      <pre>{message.content || "..."}</pre>
    </div>
  );
}
