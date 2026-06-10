import { useEffect, useState } from "react";

import { getTools, ToolInfo } from "../api";

function formatSource(item: ToolInfo) {
  const source = item.source === "local_mcp" ? "本地 MCP" : "远程 MCP";
  const transport = item.transport === "stdio" ? "本地进程" : "HTTP";
  return `${source} · ${item.server_name} · ${transport}`;
}

function getParameterEntries(schema: Record<string, unknown>) {
  const properties = schema.properties;
  const required = schema.required;

  if (!properties || typeof properties !== "object" || Array.isArray(properties)) {
    return [];
  }

  const requiredNames = Array.isArray(required)
    ? required.map((item) => String(item))
    : [];

  return Object.entries(properties as Record<string, Record<string, unknown>>).map(
    ([name, config]) => {
      const typeValue = config.type;
      const enumValue = config.enum;
      const type = Array.isArray(enumValue)
        ? enumValue.map((item) => String(item)).join(" / ")
        : typeof typeValue === "string"
          ? typeValue
          : "value";

      return {
        name,
        type,
        required: requiredNames.includes(name),
        description:
          typeof config.description === "string"
            ? config.description
            : typeof config.title === "string"
              ? config.title
              : "无额外说明",
      };
    },
  );
}

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
              <div className="tool-card-header">
                <div>
                  <h2>{item.name}</h2>
                  <span>{formatSource(item)}</span>
                </div>
              </div>
              <p className="tool-description">{item.description || "暂无工具说明"}</p>
              <div className="tool-params">
                <h3>参数说明</h3>
                {getParameterEntries(item.args_schema).length === 0 ? (
                  <p>无需参数。</p>
                ) : (
                  <ul>
                    {getParameterEntries(item.args_schema).map((param) => (
                      <li key={param.name}>
                        <strong>{param.name}</strong>
                        <span>{param.required ? "必填" : "可选"}</span>
                        <em>{param.type}</em>
                        <p>{param.description}</p>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
