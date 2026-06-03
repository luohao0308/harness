import { Link, useSearchParams } from "react-router-dom";
import { CheckCircle2 } from "lucide-react";

import { Button } from "../../../components/ui/button";
import { Card } from "../../../components/ui/card";

export function OAuthCallbackPage() {
  const [searchParams] = useSearchParams();
  const provider = searchParams.get("provider") ?? "oauth";
  const state = searchParams.get("state") ?? "";

  return (
    <main className="flex min-h-screen items-center justify-center bg-page px-4 py-8">
      <Card className="w-full max-w-md p-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-md bg-emerald-50 text-emerald-700">
          <CheckCircle2 className="h-4 w-4" />
        </div>
        <h1 className="mt-3 text-lg font-semibold text-slate-950">OAuth 回调已收到</h1>
        <p className="mt-1 text-sm leading-6 text-slate-500">
          当前后端提供 {provider} OAuth 接入占位返回；正式 provider secret 配置完成后，这里会交换 code 并写入登录 token。
        </p>
        {state ? <div className="mt-3 rounded-md bg-slate-50 px-3 py-2 font-mono text-[11px] text-slate-500">state {state}</div> : null}
        <div className="mt-5 flex gap-2">
          <Link to="/login" className="flex-1">
            <Button className="w-full">返回登录</Button>
          </Link>
          <Link to="/" className="flex-1">
            <Button variant="primary" className="w-full">进入控制台</Button>
          </Link>
        </div>
      </Card>
    </main>
  );
}
