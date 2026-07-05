import { FormEvent, useEffect, useState } from "react";
import { ChartLineUp } from "@phosphor-icons/react";

import { ApiMessage, getHealth } from "../api";
import { useChatStream } from "../hooks/useChatStream";
import { useMessages } from "../hooks/useMessages";
import { useThreads } from "../hooks/useThreads";
import { AgentMode, AgentModeConfig } from "./AgentModeConfig";
import { FileUpload } from "./FileUpload";
import { MessageInput } from "./MessageInput";
import { ChatMessage, MessageItem, MessageList } from "./MessageList";
import { PlanStep, PlanView } from "./PlanView";
import { ThreadList } from "./ThreadList";

function toChatMessage(message: ApiMessage): ChatMessage {
  return {
    id: message.id,
    role: message.role,
    content: message.content,
  };
}

function createClientMessageId() {
  return Date.now() + Math.random();
}

function toStringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function toNumberValue(value: unknown): number | null {
  return typeof value === "number" ? value : null;
}

function createPlanStep(text: string): PlanStep {
  return {
    id: createClientMessageId(),
    text,
    status: "pending",
  };
}

export function ChatPage() {
  const [health, setHealth] = useState("checking");
  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [planSteps, setPlanSteps] = useState<PlanStep[]>([]);
  const [draft, setDraft] = useState("");
  const [threadId, setThreadId] = useState<string>();
  const [ragEnabled, setRagEnabled] = useState(false);
  const [agentMode, setAgentMode] = useState<AgentMode>("react");

  const { errorMessage, isLoading, sendMessage, status, stop } = useChatStream();
  const { threads, isLoadingThreads, loadThreads } = useThreads();
  const { isLoadingMessages, loadMessages } = useMessages();

  useEffect(() => {
    getHealth()
      .then((data) => setHealth(data.status))
      .catch(() => setHealth("offline"));

    void loadThreads();
  }, [loadThreads]);

  function handleNewThread() {
    setThreadId(undefined);
    setMessages([]);
    setPlanSteps([]);
    setDraft("");
  }

  async function handleSelectThread(selectedThreadId: string) {
    setThreadId(selectedThreadId);
    setDraft("");
    setPlanSteps([]);

    const data = await loadMessages(selectedThreadId);
    setMessages(data.map(toChatMessage));
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const content = draft.trim();
    if (!content || isLoading) return;

    const userMessageId = createClientMessageId();
    const assistantMessageId = createClientMessageId();

    setMessages((current) => [
      ...current,
      { id: userMessageId, role: "user", content },
      { id: assistantMessageId, role: "assistant", content: "" },
    ]);
    setPlanSteps([]);
    setDraft("");

    void sendMessage({
      message: content,
      threadId,
      ragEnabled,
      mode: agentMode,
      onMetadata: (data) => {
        const nextThreadId = toStringValue(data.thread_id);
        if (nextThreadId) {
          setThreadId(nextThreadId);
        }
      },
      onToken: (token) => {
        setMessages((current) =>
          current.map((message) =>
            message.role === "assistant" && message.id === assistantMessageId
              ? { ...message, content: message.content + token }
              : message,
          ),
        );
      },
      onToolStart: (data) => {
        setMessages((current) => [
          ...current,
          {
            id: createClientMessageId(),
            role: "tool",
            event: "start",
            tool: toStringValue(data.tool) || "unknown",
            content: toStringValue(data.input),
          },
        ]);
      },
      onToolResult: (data) => {
        setMessages((current) => [
          ...current,
          {
            id: createClientMessageId(),
            role: "tool",
            event: "result",
            tool: toStringValue(data.tool) || "unknown",
            content: toStringValue(data.output),
          },
        ]);
      },
      onPlan: (data) => {
        const steps = Array.isArray(data.steps)
          ? data.steps.map((step) => String(step))
          : [];

        setPlanSteps(steps.map(createPlanStep));
      },
      onStepStart: (data) => {
        const stepIndex = toNumberValue(data.step_index);
        if (stepIndex === null) return;

        const stepText = toStringValue(data.step);
        setPlanSteps((current) =>
          current.map((step, index) =>
            index === stepIndex
              ? {
                  ...step,
                  text: stepText || step.text,
                  status: "running",
                }
              : step,
          ),
        );
      },
      onStepResult: (data) => {
        const stepIndex = toNumberValue(data.step_index);
        if (stepIndex === null) return;

        setPlanSteps((current) =>
          current.map((step, index) =>
            index === stepIndex
              ? {
                  ...step,
                  status: "done",
                  result: toStringValue(data.result),
                }
              : step,
          ),
        );
      },
      onError: (message) => {
        setMessages((current) =>
          current.map((item) =>
            item.role === "assistant" && item.id === assistantMessageId
              ? { ...item, content: `请求失败：${message}` }
              : item,
          ),
        );
      },
      onEnd: () => {
        void loadThreads();
      },
    });
  }

  return (
    <main className="page">
      <div className="app-layout">
        <ThreadList
          threads={threads}
          activeThreadId={threadId}
          isLoading={isLoadingThreads}
          onNewThread={handleNewThread}
          onSelectThread={(selectedThreadId) => {
            void handleSelectThread(selectedThreadId);
          }}
        />

        <section className="chat-shell">
          <header className="chat-header">
            <div className="chat-heading">
              <h1>Personal QA Assistant</h1>
              <p className={`health-status ${health}`}>
                <span aria-hidden="true" />
                Backend {health}
              </p>
            </div>
            <div className="chat-header-actions">
              <AgentModeConfig
                mode={agentMode}
                onSave={setAgentMode}
                disabled={isLoading}
              />
              <FileUpload />
            </div>
          </header>

          {isLoadingMessages ? (
            <div className="empty-chat">加载历史消息中...</div>
          ) : messages.length === 0 ? (
            <div className="empty-chat">
              <ChartLineUp size={28} weight="duotone" aria-hidden="true" />
              <h2>准备好开始新的研究</h2>
              <p>当前会话还没有消息。</p>
            </div>
          ) : (
            <div className="conversation">
              <PlanView steps={planSteps} />
              <MessageList messages={messages} />
            </div>
          )}

          <MessageInput
            draft={draft}
            errorMessage={errorMessage}
            isLoading={isLoading}
            ragEnabled={ragEnabled}
            status={status}
            onChangeDraft={setDraft}
            onChangeRagEnabled={setRagEnabled}
            onSubmit={handleSubmit}
            onStop={stop}
          />
        </section>
      </div>
    </main>
  );
}
