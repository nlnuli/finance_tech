import { ChangeEvent, useId, useState } from "react";

import { uploadFile } from "../api";

export function FileUpload() {
  const inputId = useId();
  const [selectedFile, setSelectedFile] = useState<File>();
  const [status, setStatus] = useState("");
  const [isUploading, setIsUploading] = useState(false);

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    setSelectedFile(event.target.files?.[0]);
    setStatus("");
  }

  async function handleUpload() {
    if (!selectedFile || isUploading) return;

    setIsUploading(true);
    setStatus("上传中...");

    try {
      const result = await uploadFile(selectedFile);
      setStatus(`已上传：${result.file.original_name}，切分 ${result.chunks.length} 段`);
      setSelectedFile(undefined);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "上传失败");
    } finally {
      setIsUploading(false);
    }
  }

  return (
    <div className="file-upload">
      <input id={inputId} type="file" onChange={handleFileChange} />
      <label className="file-picker" htmlFor={inputId}>
        选择文件
      </label>
      <span>{selectedFile?.name || status || "未选择文件"}</span>
      <button type="button" onClick={handleUpload} disabled={!selectedFile || isUploading}>
        {isUploading ? "上传中" : "上传文件"}
      </button>
    </div>
  );
}
