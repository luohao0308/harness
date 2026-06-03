const items = [
  {
    title: "生产部署加固",
    body: "Compose/Caddy、Helm、备份恢复、readiness probe 与外部告警通道已经进入发布路径。",
  },
  {
    title: "首次运行体验",
    body: "Dashboard、四步 onboarding、Demo 数据加载和快捷操作统一到控制台首页。",
  },
  {
    title: "前端体验修复",
    body: "错误边界、SSE 自动重连、友好错误提示、Skeleton 与错误上报已接入。",
  },
];

export function WhatsNewPanel() {
  return (
    <div className="grid gap-2">
      {items.map((item) => (
        <div key={item.title} className="rounded-md border border-slate-100 bg-slate-50/70 p-3">
          <div className="text-xs font-semibold text-slate-900">{item.title}</div>
          <p className="mt-1 text-[11px] leading-5 text-slate-500">{item.body}</p>
        </div>
      ))}
    </div>
  );
}
