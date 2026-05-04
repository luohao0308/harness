import { MarketingShell } from "./MarketingShell";
import { ShieldCheck, KeyRound, Box, FileSearch, Database, Play } from "lucide-react";

export function Security({ onNav }: { onNav?: (k: string) => void }) {
  const modules = [
    { i: <KeyRound className="w-4 h-4" />, t: "Bearer Token 鉴权", s: "所有 API 通过 Authorization: Bearer 验证，无 Token 拒绝。" },
    { i: <ShieldCheck className="w-4 h-4" />, t: "角色权限（engineer / admin）", s: "engineer 可读写任务与查询审计；admin 可写入 Settings，写入动作生成 ADMIN_ACTION。" },
    { i: <Box className="w-4 h-4" />, t: "Docker Sandbox 隔离", s: "工具调用全部下放容器，默认禁用网络与受控文件系统。" },
    { i: <FileSearch className="w-4 h-4" />, t: "Tool risk_level 与 requires_sandbox", s: "工具注册时声明风险等级与是否必须沙箱，运行时由策略校验。" },
    { i: <Database className="w-4 h-4" />, t: "Event Store 审计链", s: "append-only 事件存储构成不可篡改的执行链路，可导出审计。" },
    { i: <FileSearch className="w-4 h-4" />, t: "Model Call / Tool Call 审计", s: "每次模型调用与工具调用单独入审计表，独立查询。" },
    { i: <ShieldCheck className="w-4 h-4" />, t: "ADMIN_ACTION 审计", s: "Settings 等高风险写入操作生成 ADMIN_ACTION 记录。" },
    { i: <Play className="w-4 h-4" />, t: "Replay 故障复盘", s: "通过 Replay 接口重建任意时刻状态，复盘安全事件。" },
  ];

  const perms: Array<[string, string, string]> = [
    ["GET /api/tasks · /api/tasks/{id} · /api/tasks/{id}/result", "✓", "✓"],
    ["POST /api/tasks · /start · /cancel · /resume", "✓", "✓"],
    ["GET /api/tasks/{id}/events · POST /api/tasks/{id}/replay", "✓", "✓"],
    ["GET /api/tasks/{id}/events/stream (SSE)", "✓", "✓"],
    ["GET /api/tasks/{id}/subagents · POST /api/subagents/{id}/cancel", "✓", "✓"],
    ["GET /api/sandboxes · /api/sandboxes/{id}", "✓", "✓"],
    ["POST /api/sandboxes/{id}/terminate", "✓", "✓"],
    ["GET /api/sandboxes/warm-pool", "✓", "✓"],
    ["GET /api/tasks/{id}/model-calls · /api/tasks/{id}/tool-calls", "✓", "✓"],
    ["Settings 写入生成 ADMIN_ACTION", "—", "✓"],
    ["GET /api/settings/models · /api/settings/policies", "✓", "✓"],
    ["PUT /api/settings/models · /api/settings/policies", "—", "✓"],
    ["GET /metrics · /openapi.json · /openapi.yaml", "✓", "✓"],
  ];

  const audits: Array<[string, string, string, string]> = [
    ["TASK", "任务状态机变更", "Event Store", "GET /api/tasks/{id}/events"],
    ["MODEL", "模型调用记录（provider / model / tokens）", "Model Call Audit", "GET /api/tasks/{id}/model-calls"],
    ["TOOL", "工具调用记录（tool / args / result / sandbox）", "Tool Call Audit", "GET /api/tasks/{id}/tool-calls"],
    ["POLICY", "策略生效与拒绝事件", "Event Store + Tool Audit", "GET /api/tasks/{id}/events"],
    ["ADMIN_ACTION", "Settings 写入等高风险操作", "Admin Audit 表", "Settings PUT 写入"],
  ];

  return (
    <MarketingShell active="security" onNav={onNav}>
      <section className="border-b border-slate-200">
        <div className="max-w-[1320px] mx-auto px-4 sm:px-8 py-12">
          <div className="text-[12px] tracking-widest text-slate-500 mb-2">SECURITY</div>
          <h1 className="text-[32px] sm:text-[40px] tracking-tight text-slate-900 mb-3">
            基于当前实现的安全与审计能力
          </h1>
          <p className="text-slate-600 text-[14px] max-w-2xl">
            本页只列举当前后端已经实现的安全机制：Bearer 鉴权、角色权限、Sandbox 隔离与四类审计。
            未实现的 SSO / LDAP / SAML / 审计签名 / 密钥轮换不在此处展示。
          </p>
        </div>
      </section>

      <section className="border-b border-slate-200 bg-slate-50/40">
        <div className="max-w-[1320px] mx-auto px-4 sm:px-8 py-12">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
            {modules.map((m) => (
              <div key={m.t} className="bg-white border border-slate-200 rounded-lg p-4">
                <div className="w-7 h-7 rounded bg-slate-100 flex items-center justify-center text-slate-600 mb-2">
                  {m.i}
                </div>
                <div className="text-[13px] text-slate-900 mb-1">{m.t}</div>
                <p className="text-[12px] text-slate-600 leading-relaxed">{m.s}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="border-b border-slate-200">
        <div className="max-w-[1320px] mx-auto px-4 sm:px-8 py-12">
          <h2 className="text-slate-900 tracking-tight mb-1">权限矩阵</h2>
          <p className="text-[12px] text-slate-500 mb-5">engineer / admin 两类角色对当前接口的权限范围。</p>
          <div className="border border-slate-200 rounded-lg bg-white overflow-x-auto">
            <table className="w-full text-[12px] min-w-[640px]">
              <thead className="bg-slate-50 text-slate-500">
                <tr className="text-left">
                  <th className="font-normal px-3 py-2.5">接口类型</th>
                  <th className="font-normal px-3 py-2.5 w-32">engineer</th>
                  <th className="font-normal px-3 py-2.5 w-32">admin</th>
                </tr>
              </thead>
              <tbody>
                {perms.map((r) => (
                  <tr key={r[0]} className="border-t border-slate-100">
                    <td className="px-3 py-2.5 font-mono text-slate-700 text-[11px]">{r[0]}</td>
                    <td className="px-3 py-2.5 text-slate-700">{r[1]}</td>
                    <td className="px-3 py-2.5 text-slate-700">{r[2]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="border-b border-slate-200 bg-slate-50/40">
        <div className="max-w-[1320px] mx-auto px-4 sm:px-8 py-12">
          <h2 className="text-slate-900 tracking-tight mb-1">审计矩阵</h2>
          <p className="text-[12px] text-slate-500 mb-5">五类审计通道独立可查，构成完整的合规链路。</p>
          <div className="border border-slate-200 rounded-lg bg-white overflow-x-auto">
            <table className="w-full text-[12px] min-w-[760px]">
              <thead className="bg-slate-50 text-slate-500">
                <tr className="text-left">
                  <th className="font-normal px-3 py-2.5">审计类型</th>
                  <th className="font-normal px-3 py-2.5">记录内容</th>
                  <th className="font-normal px-3 py-2.5">存储位置</th>
                  <th className="font-normal px-3 py-2.5">查询接口</th>
                </tr>
              </thead>
              <tbody>
                {audits.map((r) => (
                  <tr key={r[0]} className="border-t border-slate-100">
                    <td className="px-3 py-2.5 text-slate-900 font-mono">{r[0]}</td>
                    <td className="px-3 py-2.5 text-slate-700">{r[1]}</td>
                    <td className="px-3 py-2.5 text-slate-600">{r[2]}</td>
                    <td className="px-3 py-2.5 font-mono text-[11px] text-slate-600">{r[3]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </MarketingShell>
  );
}
