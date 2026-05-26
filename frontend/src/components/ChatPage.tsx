import { FormEvent, useEffect, useState } from "react";

import { ApiMessage, getHealth } from "../api";
import { useChatStream } from "../hooks/useChatStream";
import { useMessages } from "../hooks/useMessages";
import { useThreads } from "../hooks/useThreads";
import { FileUpload } from "./FileUpload";
import { ChatMessage, MessageItem, MessageList } from "./MessageList";
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

export function ChatPage() {
  const [health, setHealth] = useState("checking");
  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [draft, setDraft] = useState("");
  const [threadId, setThreadId] = useState<string>();
  const [ragEnabled, setRagEnabled] = useState(false);

  const { isLoading, sendMessage } = useChatStream();
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
    setDraft("");
  }

  async function handleSelectThread(selectedThreadId: string) {
    setThreadId(selectedThreadId);
    setDraft("");

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
    setDraft("");

    void sendMessage({
      message: content,
      threadId,
      ragEnabled,
      onMetadata: (data) => {
        if (data.thread_id) {
          setThreadId(data.thread_id);
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
            tool: data.tool ?? "unknown",
            content: data.input ?? "",
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
            tool: data.tool ?? "unknown",
            content: data.output ?? "",
          },
        ]);
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
            <div>
              <h1>Personal QA Assistant</h1>
              <p>Backend health: {health}</p>
            </div>
            <FileUpload />
          </header>

          {isLoadingMessages ? (
            <div className="empty-chat">加载历史消息中...</div>
          ) : messages.length === 0 ? (
            <div className="empty-chat">开始一个新问题，或从左侧选择历史对话。</div>
          ) : (
            <MessageList messages={messages} />
          )}

          <form className="composer" onSubmit={handleSubmit}>
            <label className="rag-toggle">
              <input
                type="checkbox"
                checked={ragEnabled}
                onChange={(event) => setRagEnabled(event.target.checked)}
                disabled={isLoading}
              />
              <span>RAG</span>
            </label>
            <input
              aria-label="Message"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="输入问题..."
              disabled={isLoading}
            />
            <button type="submit" disabled={isLoading}>
              {isLoading ? "生成中" : "发送"}
            </button>
          </form>
        </section>
      </div>
    </main>
  );
}
