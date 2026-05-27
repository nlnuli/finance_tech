export type PlanStep = {
  id: number;
  text: string;
  status: "pending" | "running" | "done";
  result?: string;
};

type PlanViewProps = {
  steps: PlanStep[];
};

export function PlanView({ steps }: PlanViewProps) {
  if (steps.length === 0) {
    return null;
  }

  return (
    <section className="plan-view" aria-label="Plan steps">
      <h2>Plan</h2>
      <ol>
        {steps.map((step, index) => (
          <li className={`plan-step ${step.status}`} key={step.id}>
            <div>
              <span>{index + 1}</span>
              <strong>{step.text}</strong>
              <em>
                {step.status === "running"
                  ? "执行中"
                  : step.status === "done"
                    ? "完成"
                    : "等待"}
              </em>
            </div>
            {step.result ? <pre>{step.result}</pre> : null}
          </li>
        ))}
      </ol>
    </section>
  );
}
