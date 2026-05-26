import { useState } from "react";

import { ChatPage } from "./components/ChatPage";
import { ToolsPage } from "./components/ToolsPage";

export default function App() {
  const [page, setPage] = useState<"chat" | "tools">("chat");

  return (
    <>
      <nav className="top-nav">
        <button
          className={page === "chat" ? "active" : ""}
          type="button"
          onClick={() => setPage("chat")}
        >
          Chat
        </button>
        <button
          className={page === "tools" ? "active" : ""}
          type="button"
          onClick={() => setPage("tools")}
        >
          Tools
        </button>
      </nav>
      {page === "chat" ? <ChatPage /> : <ToolsPage />}
    </>
  );
}
