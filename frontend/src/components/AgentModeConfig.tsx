import { useEffect, useState } from "react";

export type AgentMode = "chat" | "react" | "plan_solve";

type AgentModeConfigProps = {
  mode: AgentMode;
  onSave: (mode: AgentMode) => void;
  disabled?: boolean;
};

const MODE_OPTIONS: Array<{
  value: AgentMode;
  label: string;
  description: string;
}> = [
  {
    value: "chat",
    label: "Chat",
    description: "普通聊天，不主动调用工具，适合简单问答。",
  },
  {
    value: "react",
    label: "ReAct",
    description: "模型可自行决定是否调用工具，适合检索、计算和时间查询。",
  },
  {
    value: "plan_solve",
    label: "Plan-Solve",
    description: "先生成计划，再逐步执行并总结，适合分析、比较和多步骤问题。",
  },
];

export function AgentModeConfig({ mode, onSave, disabled }: AgentModeConfigProps) {
  const [draftMode, setDraftMode] = useState<AgentMode>(mode);

  useEffect(() => {
    setDraftMode(mode);
  }, [mode]);

  return (
    <div className="agent-mode-config">
      <span>Agent Mode</span>
      <div className="agent-mode-options">
        {MODE_OPTIONS.map((option) => (
          <label
            className={draftMode === option.value ? "active" : ""}
            key={option.value}
          >
            <input
              type="radio"
              name="agent-mode"
              value={option.value}
              checked={draftMode === option.value}
              disabled={disabled}
              onChange={() => setDraftMode(option.value)}
            />
            <strong>{option.label}</strong>
            <small>{option.description}</small>
          </label>
        ))}
      </div>
      <button
        type="button"
        disabled={disabled || draftMode === mode}
        onClick={() => onSave(draftMode)}
      >
        保存模式
      </button>
    </div>
  );
}
