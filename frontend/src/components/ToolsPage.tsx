import { useEffect, useState } from "react";

import { getTools, ToolInfo } from "../api";

export function ToolsPage() {
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [status, setStatus] = useState("加载工具中...");

  useEffect(() => {
    getTools()
      .then((data) => {
        setTools(data);
        setStatus("");
      })
      .catch(() => {
        setStatus("工具加载失败");
      });
  }, []);

  return (
    <main className="page">
      <section className="tools-page">
        <header className="tools-header">
          <h1>Tools</h1>
          <p>当前后端可用工具</p>
        </header>

        {status ? <div className="empty-chat">{status}</div> : null}

        <div className="tool-list">
          {tools.map((item) => (
            <article className="tool-card" key={item.name}>
              <div>
                <h2>{item.name}</h2>
                <span>{item.type}</span>
              </div>
              <p>{item.description}</p>
              <pre>{JSON.stringify(item.args_schema, null, 2)}</pre>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
