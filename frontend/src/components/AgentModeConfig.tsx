export type AgentMode = "chat" | "react" | "plan_solve";

type AgentModeConfigProps = {
  mode: AgentMode;
  onSave: (mode: AgentMode) => void;
  disabled?: boolean;
};

const MODE_OPTIONS: Array<{
  value: AgentMode;
  label: string;
}> = [
  {
    value: "chat",
    label: "Chat",
  },
  {
    value: "react",
    label: "ReAct",
  },
  {
    value: "plan_solve",
    label: "Plan-Solve",
  },
];

export function AgentModeConfig({ mode, onSave, disabled }: AgentModeConfigProps) {
  return (
    <div className="agent-mode-config">
      <div className="agent-mode-options" role="radiogroup" aria-label="Agent mode">
        {MODE_OPTIONS.map((option) => (
          <label
            className={mode === option.value ? "active" : ""}
            key={option.value}
          >
            <input
              type="radio"
              name="agent-mode"
              value={option.value}
              checked={mode === option.value}
              disabled={disabled}
              onChange={() => onSave(option.value)}
            />
            <strong>{option.label}</strong>
          </label>
        ))}
      </div>
    </div>
  );
}
