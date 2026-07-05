import { ChatCircle, Plus } from "@phosphor-icons/react";

import { Thread } from "../api";

type ThreadListProps = {
  threads: Thread[];
  activeThreadId?: string;
  isLoading: boolean;
  onNewThread: () => void;
  onSelectThread: (threadId: string) => void;
};

export function ThreadList({
  threads,
  activeThreadId,
  isLoading,
  onNewThread,
  onSelectThread,
}: ThreadListProps) {
  return (
    <aside className="thread-list">
      <button className="new-thread-button" type="button" onClick={onNewThread}>
        <Plus size={17} weight="bold" aria-hidden="true" />
        <span>新对话</span>
      </button>

      <div className="thread-list-title">
        <span>历史对话</span>
        <strong>{threads.length}</strong>
      </div>

      {isLoading ? <p className="thread-list-empty">加载中...</p> : null}

      {!isLoading && threads.length === 0 ? (
        <p className="thread-list-empty">暂无历史对话</p>
      ) : null}

      <div className="thread-items">
        {threads.map((thread) => (
          <button
            className={`thread-item ${
              thread.id === activeThreadId ? "active" : ""
            }`}
            key={thread.id}
            type="button"
            aria-current={thread.id === activeThreadId ? "true" : undefined}
            onClick={() => onSelectThread(thread.id)}
          >
            <ChatCircle size={16} aria-hidden="true" />
            <span>{thread.title || "未命名对话"}</span>
          </button>
        ))}
      </div>
    </aside>
  );
}
