import { FormEvent, useEffect, useState } from "react";

import { getHealth } from "../api";
import { useChatStream } from "../hooks/useChatStream";

type Message = {
  id: number;
  role: "assistant" | "user";
  content: string;
};

const initialMessages: Message[] = [
  {
    id: 1,
    role: "assistant",
    content: "你好，我是你的个人问答助手。可以先输入一个问题试试。",
  },
];

export function ChatPage() {
  const [health, setHealth] = useState("checking");
  const [messages, setMessages] = useState<Message[]>(initialMessages);
  const [draft, setDraft] = useState("");
  const [threadId, setThreadId] = useState<string>();
  const { isLoading, sendMessage } = useChatStream();

  useEffect(() => {
    getHealth()
      .then((data) => setHealth(data.status))
      .catch(() => setHealth("offline"));
  }, []);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const content = draft.trim();
    if (!content || isLoading) return;

    const userMessageId = Date.now();
    const assistantMessageId = userMessageId + 1;

    setMessages((current) => [
      ...current,
      { id: userMessageId, role: "user", content },
      { id: assistantMessageId, role: "assistant", content: "" },
    ]);
    setDraft("");

    void sendMessage({
      message: content,
      threadId,
      onMetadata: (data) => {
        if (data.thread_id) {
          setThreadId(data.thread_id);
        }
      },
      onToken: (token) => {
        setMessages((current) =>
          current.map((message) =>
            message.id === assistantMessageId
              ? { ...message, content: message.content + token }
              : message,
          ),
        );
      },
      onError: (message) => {
        setMessages((current) =>
          current.map((item) =>
            item.id === assistantMessageId
              ? { ...item, content: `请求失败：${message}` }
              : item,
          ),
        );
      },
    });
  }

  return (
    <main className="page">
      <section className="chat-shell">
        <header className="chat-header">
          <div>
            <h1>Personal QA Assistant</h1>
            <p>Backend health: {health}</p>
          </div>
        </header>

        <div className="messages" aria-live="polite">
          {messages.map((message) => (
            <div className={`message ${message.role}`} key={message.id}>
              <span>{message.role === "assistant" ? "Assistant" : "You"}</span>
              <p>{message.content || "..."}</p>
            </div>
          ))}
        </div>

        <form className="composer" onSubmit={handleSubmit}>
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
    </main>
  );
}
