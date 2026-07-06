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
      <summary>
        <CaretRight className="tool-event-caret" size={14} weight="bold" aria-hidden="true" />
        <Wrench size={14} weight="bold" aria-hidden="true" />
        <span>{title}</span>
      </summary>
      <pre>{message.content || "..."}</pre>
    </details>
  );
}
import { CaretRight, Wrench } from "@phosphor-icons/react";
