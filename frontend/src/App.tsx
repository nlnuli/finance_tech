import { useEffect, useState } from "react";
import { ChartLineUp, ChatCircleDots, SignOut, Wrench } from "@phosphor-icons/react";

import {
  AuthUser,
  clearAuthSession,
  getMe,
  getStoredUser,
  storeAuthSession,
} from "./api";
import { AuthGate } from "./components/AuthGate";
import { ChatPage } from "./components/ChatPage";
import { ToolsPage } from "./components/ToolsPage";

export default function App() {
  const [page, setPage] = useState<"chat" | "tools">("chat");
  const [user, setUser] = useState<AuthUser | null>(() => getStoredUser());
  const [isCheckingAuth, setIsCheckingAuth] = useState(Boolean(getStoredUser()));

  useEffect(() => {
    if (!user) return;
    getMe()
      .then((freshUser) => {
        setUser(freshUser);
        const token = localStorage.getItem("finance_tech_auth_token");
        if (token) {
          storeAuthSession({
            access_token: token,
            token_type: "bearer",
            user: freshUser,
          });
        }
      })
      .catch(() => {
        clearAuthSession();
        setUser(null);
      })
      .finally(() => setIsCheckingAuth(false));
  }, []);

  useEffect(() => {
    function handleAuthCleared() {
      setUser(null);
      setPage("chat");
    }
    window.addEventListener("finance-tech-auth-cleared", handleAuthCleared);
    return () => {
      window.removeEventListener("finance-tech-auth-cleared", handleAuthCleared);
    };
  }, []);

  function handleLogout() {
    clearAuthSession();
    setUser(null);
    setPage("chat");
  }

  if (isCheckingAuth) {
    return (
      <div className="auth-loading">
        <ChartLineUp size={24} weight="duotone" aria-hidden="true" />
        Checking secure workspace...
      </div>
    );
  }

  if (!user) {
    return <AuthGate onAuthenticated={setUser} />;
  }

  return (
    <div className="app-frame">
      <header className="app-bar">
        <div className="app-brand">
          <span className="app-brand-mark" aria-hidden="true">
            <ChartLineUp size={19} weight="bold" />
          </span>
          <strong>Finance Tech</strong>
        </div>
        <nav className="top-nav" aria-label="Primary navigation">
          <button
            className={page === "chat" ? "active" : ""}
            type="button"
            aria-current={page === "chat" ? "page" : undefined}
            onClick={() => setPage("chat")}
          >
            <ChatCircleDots size={17} weight="bold" aria-hidden="true" />
            <span>Chat</span>
          </button>
          <button
            className={page === "tools" ? "active" : ""}
            type="button"
            aria-current={page === "tools" ? "page" : undefined}
            onClick={() => setPage("tools")}
          >
            <Wrench size={17} weight="bold" aria-hidden="true" />
            <span>Tools</span>
          </button>
        </nav>
        <div className="workspace-state">
          <span aria-hidden="true" />
          {user.email}
        </div>
        <button className="logout-button" type="button" onClick={handleLogout}>
          <SignOut size={16} weight="bold" aria-hidden="true" />
          Logout
        </button>
      </header>
      {page === "chat" ? <ChatPage /> : <ToolsPage />}
    </div>
  );
}
