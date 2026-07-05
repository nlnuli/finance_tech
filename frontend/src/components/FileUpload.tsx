import { ChangeEvent, useId, useRef, useState } from "react";
import {
  CheckCircle,
  CircleNotch,
  FileArrowUp,
  UploadSimple,
  WarningCircle,
} from "@phosphor-icons/react";

import { uploadFile } from "../api";

type UploadPhase = "idle" | "uploading" | "processing" | "success" | "error";

function formatFileSize(size: number): string {
  if (size < 1024 * 1024) {
    return `${Math.max(1, Math.round(size / 1024))} KB`;
  }
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function UploadStatusIcon({ phase }: { phase: UploadPhase }) {
  if (phase === "success") {
    return <CheckCircle size={15} weight="fill" aria-hidden="true" />;
  }
  if (phase === "error") {
    return <WarningCircle size={15} weight="fill" aria-hidden="true" />;
  }
  return <CircleNotch className="spin" size={15} weight="bold" aria-hidden="true" />;
}

export function FileUpload() {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File>();
  const [phase, setPhase] = useState<UploadPhase>("idle");
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState("未选择文件");
  const [isUploading, setIsUploading] = useState(false);

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    setSelectedFile(file);
    setPhase("idle");
    setProgress(0);
    setStatus(file ? `${file.name} · ${formatFileSize(file.size)}` : "未选择文件");
  }

  async function handleUpload() {
    if (!selectedFile || isUploading) return;

    setIsUploading(true);
    setPhase("uploading");
    setProgress(0);
    setStatus(`正在上传 ${selectedFile.name}`);

    try {
      const result = await uploadFile(selectedFile, {
        onProgress: setProgress,
        onUploadComplete: () => {
          setPhase("processing");
          setStatus("文件已上传，正在解析并写入知识库");
        },
      });
      if (result.file.status !== "ready") {
        throw new Error(`上传未完成：文件状态为 ${result.file.status}`);
      }
      setPhase("success");
      setStatus(
        `已就绪：${result.file.original_name} · ${result.file.page_count ?? 0} 页 · ${result.file.chunk_count} 个分块`,
      );
      setSelectedFile(undefined);
      if (inputRef.current) {
        inputRef.current.value = "";
      }
    } catch (error) {
      setPhase("error");
      setStatus(error instanceof Error ? error.message : "上传失败");
    } finally {
      setIsUploading(false);
    }
  }

  return (
    <div className={`file-upload ${phase}`}>
      <div className="file-upload-controls">
        <input ref={inputRef} id={inputId} type="file" onChange={handleFileChange} />
        <label
          className={`file-picker ${isUploading ? "disabled" : ""}`}
          htmlFor={isUploading ? undefined : inputId}
        >
          <FileArrowUp size={16} weight="bold" aria-hidden="true" />
          <span>选择文件</span>
        </label>
        <span className="file-upload-summary" title={status}>
          {selectedFile
            ? `${selectedFile.name} · ${formatFileSize(selectedFile.size)}`
            : phase === "success"
              ? "上传完成"
              : "未选择文件"}
        </span>
        <button type="button" onClick={handleUpload} disabled={!selectedFile || isUploading}>
          <UploadSimple size={16} weight="bold" aria-hidden="true" />
          <span>
            {phase === "uploading" ? `${progress}%` : phase === "processing" ? "处理中" : "上传"}
          </span>
        </button>
      </div>

      {phase !== "idle" ? (
        <div className="upload-feedback" role="status" aria-live="polite">
          <div className="upload-status-line">
            <UploadStatusIcon phase={phase} />
            <span>{status}</span>
            {phase === "uploading" ? <strong>{progress}%</strong> : null}
          </div>
          {phase === "uploading" || phase === "processing" ? (
            <div
              className={`upload-progress ${phase}`}
              role="progressbar"
              aria-label={phase === "uploading" ? "文件上传进度" : "后端处理进度"}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={phase === "uploading" ? progress : undefined}
            >
              <span style={{ width: phase === "uploading" ? `${progress}%` : "38%" }} />
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
