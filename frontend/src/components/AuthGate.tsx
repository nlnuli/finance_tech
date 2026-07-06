import { FormEvent, useState } from "react";
import { ChartLineUp, LockKey, SignIn, UserPlus } from "@phosphor-icons/react";

import {
  AuthUser,
  loginUser,
  registerUser,
  storeAuthSession,
} from "../api";

type AuthGateProps = {
  onAuthenticated: (user: AuthUser) => void;
};

type AuthMode = "login" | "register";

export function AuthGate({ onAuthenticated }: AuthGateProps) {
  const [mode, setMode] = useState<AuthMode>("login");
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);
    try {
      const response =
        mode === "login"
          ? await loginUser(email, password)
            : await registerUser(email, password, displayName);
      storeAuthSession(response);
      onAuthenticated(response.user);
    } catch (authError) {
      const message = authError instanceof Error ? authError.message : "认证失败";
      setError(message === "Failed to fetch" ? "无法连接后端服务" : message);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-panel" aria-label="Finance Tech authentication">
        <div className="auth-brand">
          <span className="app-brand-mark" aria-hidden="true">
            <ChartLineUp size={21} weight="bold" />
          </span>
          <div>
            <strong>Finance Tech</strong>
            <p>私有研究工作台</p>
          </div>
        </div>

        <div className="auth-copy">
          <LockKey size={28} weight="duotone" aria-hidden="true" />
          <h1>{mode === "login" ? "欢迎回来" : "创建你的工作区"}</h1>
          <p>登录后访问相互隔离的会话、文件和 RAG 知识库。</p>
        </div>

        <div className="auth-tabs" role="tablist" aria-label="Authentication mode">
          <button
            className={mode === "login" ? "active" : ""}
            type="button"
            onClick={() => setMode("login")}
          >
            <SignIn size={16} weight="bold" aria-hidden="true" />
            登录
          </button>
          <button
            className={mode === "register" ? "active" : ""}
            type="button"
            onClick={() => setMode("register")}
          >
            <UserPlus size={16} weight="bold" aria-hidden="true" />
            注册
          </button>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          {mode === "register" ? (
            <label>
              <span>名称</span>
              <input
                autoComplete="name"
                maxLength={255}
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                placeholder="分析师名称"
              />
            </label>
          ) : null}
          <label>
            <span>邮箱</span>
            <input
              autoComplete="email"
              inputMode="email"
              required
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="analyst@example.com"
            />
          </label>
          <label>
            <span>密码</span>
            <input
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              minLength={mode === "register" ? 8 : undefined}
              required
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="至少 8 个字符"
            />
          </label>
          {error ? <p className="auth-error">{error}</p> : null}
          <button className="auth-submit" disabled={isSubmitting} type="submit">
            {isSubmitting
              ? "处理中..."
              : mode === "login"
                ? "登录"
                : "创建账号"}
          </button>
        </form>
      </section>
    </main>
  );
}
