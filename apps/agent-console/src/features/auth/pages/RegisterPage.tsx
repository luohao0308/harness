import { FormEvent, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { Loader2, Lock, UserPlus } from "lucide-react";

import { Button } from "../../../components/ui/button";
import { Card } from "../../../components/ui/card";
import { Input } from "../../../components/ui/input";
import { useAuth } from "../AuthProvider";
import { getAuthConfig } from "../../tasks/api";

export function RegisterPage() {
  const navigate = useNavigate();
  const { registerWithPassword } = useAuth();
  const authConfig = useQuery({
    queryKey: ["auth", "config"],
    queryFn: getAuthConfig,
    retry: false,
  });
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [organizationName, setOrganizationName] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const registrationEnabled = authConfig.data?.public_registration_enabled === true;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      await registerWithPassword({
        email,
        password,
        name,
        organization_name: organizationName || null,
      });
      navigate("/", { replace: true });
    } catch (registerError) {
      setError(registerError instanceof Error ? registerError.message : "注册失败");
    } finally {
      setPending(false);
    }
  }

  if (authConfig.isLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-page px-4 py-8">
        <Card className="w-full max-w-md p-5 text-sm text-slate-500">
          正在加载注册配置...
        </Card>
      </main>
    );
  }

  if (!registrationEnabled) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-page px-4 py-8">
        <Card className="w-full max-w-md p-5">
          <div className="flex h-9 w-9 items-center justify-center rounded-md bg-slate-100 text-slate-700">
            <Lock className="h-4 w-4" />
          </div>
          <h1 className="mt-3 text-lg font-semibold text-slate-950">注册已关闭</h1>
          <p className="mt-1 text-sm leading-6 text-slate-500">
            当前部署使用管理员邀请流程。请联系组织管理员创建账号，或使用已分配账号登录。
          </p>
          <Link to="/login" className="mt-5 block">
            <Button variant="primary" className="w-full">返回登录</Button>
          </Link>
        </Card>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-page px-4 py-8">
      <Card className="w-full max-w-md p-5">
        <div className="mb-5">
          <div className="flex h-9 w-9 items-center justify-center rounded-md bg-slate-900 text-white">
            <UserPlus className="h-4 w-4" />
          </div>
          <h1 className="mt-3 text-lg font-semibold text-slate-950">创建 Harness 工作区</h1>
          <p className="mt-1 text-sm text-slate-500">注册后会自动创建个人组织并进入控制台。</p>
        </div>
        <form className="space-y-3" onSubmit={submit}>
          <label className="block text-xs font-medium text-slate-600">
            姓名
            <Input
              className="mt-1 w-full"
              autoComplete="name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              required
            />
          </label>
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
            工作区名称
            <Input
              className="mt-1 w-full"
              value={organizationName}
              onChange={(event) => setOrganizationName(event.target.value)}
              placeholder="默认使用姓名生成"
            />
          </label>
          <label className="block text-xs font-medium text-slate-600">
            密码
            <Input
              className="mt-1 w-full"
              type="password"
              autoComplete="new-password"
              minLength={8}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>
          {error ? <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">{error}</div> : null}
          <Button type="submit" variant="primary" className="w-full" disabled={pending}>
            {pending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <UserPlus className="h-3.5 w-3.5" />}
            创建并登录
          </Button>
        </form>
        <div className="mt-4 text-center text-xs text-slate-500">
          已有账号？{" "}
          <Link className="font-medium text-slate-900 hover:underline" to="/login">
            返回登录
          </Link>
        </div>
      </Card>
    </main>
  );
}
