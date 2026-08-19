import { FormEvent, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Github, Loader2, LogIn } from "lucide-react";

import { Button } from "../../../components/ui/button";
import { Card } from "../../../components/ui/card";
import { Input } from "../../../components/ui/input";
import { useAuth } from "../AuthProvider";
import { getAuthConfig, startOAuth, startSAML } from "../../tasks/api";
import { SSOLoginButton } from "../components/SSOLoginButton";

const supportedOAuthProviders = ["github", "google"] as const;
type SupportedOAuthProvider = (typeof supportedOAuthProviders)[number];

export function LoginPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { loginWithPassword } = useAuth();
  const authConfig = useQuery({
    queryKey: ["auth", "config"],
    queryFn: getAuthConfig,
    retry: false,
  });
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const publicRegistrationEnabled = authConfig.data?.public_registration_enabled === true;
  const oauthProviders = supportedOAuthProviders.filter((provider) =>
    authConfig.data?.oauth_providers.includes(provider),
  );
  const samlProviders = authConfig.data?.saml_providers ?? [];

  async function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      await loginWithPassword({ email, password });
      navigate(searchParams.get("next") || "/", { replace: true });
    } catch (loginError) {
      setError(loginError instanceof Error ? loginError.message : "登录失败");
    } finally {
      setPending(false);
    }
  }

  async function launchOAuth(provider: SupportedOAuthProvider) {
    setPending(true);
    setError("");
    try {
      const response = await startOAuth(provider);
      window.location.assign(response.authorization_url);
    } catch (oauthError) {
      setError(oauthError instanceof Error ? oauthError.message : "无法启动 OAuth 登录");
      setPending(false);
    }
  }

  async function launchSAML(providerId: string) {
    setPending(true);
    setError("");
    try {
      const response = await startSAML(providerId);
      window.location.assign(response.redirect_url);
    } catch (samlError) {
      setError(samlError instanceof Error ? samlError.message : "无法启动 SSO 登录");
      setPending(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-page px-4 py-8">
      <Card className="w-full max-w-md p-5">
        <div className="mb-5">
          <div className="flex h-9 w-9 items-center justify-center rounded-md bg-slate-900 text-white">
            <LogIn className="h-4 w-4" />
          </div>
          <h1 className="mt-3 text-lg font-semibold text-slate-950">登录 Forge Harness Console</h1>
          <p className="mt-1 text-sm text-slate-500">使用团队账号进入工作区。</p>
        </div>
        <form className="space-y-3" onSubmit={submit}>
          <label className="block text-xs font-medium text-slate-600">
            邮箱
            <Input
              className="mt-1 w-full"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </label>
          <label className="block text-xs font-medium text-slate-600">
            密码
            <Input
              className="mt-1 w-full"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>
          {error ? <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">{error}</div> : null}
          <Button type="submit" variant="primary" className="w-full" disabled={pending}>
            {pending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <LogIn className="h-3.5 w-3.5" />}
            登录
          </Button>
        </form>
        {samlProviders.length > 0 ? (
          <div className="mt-4">
            <SSOLoginButton providers={samlProviders} onInitiateSSO={launchSAML} disabled={pending} />
          </div>
        ) : null}
        {oauthProviders.length > 0 ? (
          <div className="mt-4 grid grid-cols-2 gap-2">{oauthProviders.map((provider) => (
              <Button
                key={provider}
                type="button"
                variant="secondary"
                disabled={pending}
                onClick={() => void launchOAuth(provider)}
              >
                {provider === "github" ? <Github className="h-3.5 w-3.5" /> : null}
                {provider === "github" ? "GitHub" : "Google"}
              </Button>
            ))}
          </div>
        ) : null}
        {publicRegistrationEnabled ? (
          <div className="mt-4 text-center text-xs text-slate-500">
            还没有账号？{" "}
            <Link className="font-medium text-slate-900 hover:underline" to="/register">
              创建工作区
            </Link>
          </div>
        ) : null}
      </Card>
    </main>
  );
}
