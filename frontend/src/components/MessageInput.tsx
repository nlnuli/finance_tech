import { FormEvent } from "react";

import { StreamStatus } from "../hooks/useChatStream";

type MessageInputProps = {
  draft: string;
  errorMessage: string;
  isLoading: boolean;
  ragEnabled: boolean;
  status: StreamStatus;
  onChangeDraft: (value: string) => void;
  onChangeRagEnabled: (value: boolean) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onStop: () => void;
};

function getStatusText(status: StreamStatus, errorMessage: string) {
  if (status === "inflight") {
    return "生成中...";
  }

  if (status === "error") {
    return errorMessage || "请求失败";
  }

  if (status === "done") {
    return "已完成";
  }

  return "";
}

export function MessageInput({
  draft,
  errorMessage,
  isLoading,
  ragEnabled,
  status,
  onChangeDraft,
  onChangeRagEnabled,
  onSubmit,
  onStop,
}: MessageInputProps) {
  const statusText = getStatusText(status, errorMessage);

  return (
    <form className="composer" onSubmit={onSubmit}>
      <div className="composer-panel">
        <textarea
          aria-label="Message"
          value={draft}
          onChange={(event) => onChangeDraft(event.target.value)}
          placeholder="给 Personal QA 发送消息"
          disabled={isLoading}
          rows={1}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }}
        />
        <div className="composer-actions">
          <label className="rag-toggle">
            <input
              type="checkbox"
              checked={ragEnabled}
              onChange={(event) => onChangeRagEnabled(event.target.checked)}
              disabled={isLoading}
            />
            <span>RAG</span>
          </label>
          {isLoading ? (
            <button type="button" className="stop-button" onClick={onStop}>
              停止
            </button>
          ) : (
            <button type="submit" disabled={!draft.trim()}>
              发送
            </button>
          )}
        </div>
      </div>
      {statusText ? <p className={`composer-status ${status}`}>{statusText}</p> : null}
    </form>
  );
}
