import { FormEvent, useRef } from "react";
import { Database, PaperPlaneTilt, Stop } from "@phosphor-icons/react";

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
  const isComposingRef = useRef(false);

  return (
    <form className="composer" onSubmit={onSubmit}>
      <div className="composer-panel">
        <textarea
          aria-label="Message"
          value={draft}
          onChange={(event) => onChangeDraft(event.target.value)}
          onCompositionStart={() => {
            isComposingRef.current = true;
          }}
          onCompositionEnd={() => {
            isComposingRef.current = false;
          }}
          placeholder="给 Personal QA 发送消息"
          disabled={isLoading}
          rows={1}
          onKeyDown={(event) => {
            if (isComposingRef.current || event.nativeEvent.isComposing) {
              return;
            }
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
            <span className="toggle-track" aria-hidden="true" />
            <Database size={15} weight="bold" aria-hidden="true" />
            <span>RAG</span>
          </label>
          {isLoading ? (
            <button
              type="button"
              className="composer-submit stop-button"
              aria-label="停止生成"
              title="停止生成"
              onClick={onStop}
            >
              <Stop size={17} weight="fill" aria-hidden="true" />
            </button>
          ) : (
            <button
              type="submit"
              className="composer-submit"
              aria-label="发送消息"
              title="发送消息"
              disabled={!draft.trim()}
            >
              <PaperPlaneTilt size={18} weight="fill" aria-hidden="true" />
            </button>
          )}
        </div>
      </div>
      {statusText ? <p className={`composer-status ${status}`}>{statusText}</p> : null}
    </form>
  );
}
