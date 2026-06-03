import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { BookOpen, Check, Search } from "lucide-react";
import { useLocation } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { Skeleton } from "../../../components/ui/Skeleton";
import { cn } from "../../../lib/utils";
import { MarkdownContent } from "../components/MarkdownContent";

type HelpDoc = {
  id: string;
  title: string;
  category: string;
  path: string;
  keywords: string[];
};

type HelpIndex = {
  categories: string[];
  docs: HelpDoc[];
};

export function HelpCenterPage() {
  const location = useLocation();
  const routeDefaultId = location.pathname.endsWith("/troubleshooting")
    ? "troubleshooting"
    : "getting-started.quickstart";
  const [query, setQuery] = useState("");
  const [activeId, setActiveId] = useState(routeDefaultId);
  const [feedback, setFeedback] = useState<"yes" | "no" | null>(null);
  const index = useQuery({ queryKey: ["help", "index"], queryFn: fetchHelpIndex });
  const activeDoc = index.data?.docs.find((doc) => doc.id === activeId) ?? index.data?.docs[0];
  const content = useQuery({
    queryKey: ["help", activeDoc?.id],
    queryFn: () => fetchHelpDoc(activeDoc?.path ?? ""),
    enabled: Boolean(activeDoc?.path),
  });
  const filteredDocs = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const docs = index.data?.docs ?? [];
    if (!needle) return docs;
    return docs.filter((doc) =>
      [doc.title, doc.category, ...doc.keywords].join(" ").toLowerCase().includes(needle),
    );
  }, [index.data?.docs, query]);

  useEffect(() => {
    setActiveId(routeDefaultId);
    setFeedback(null);
  }, [routeDefaultId]);

  return (
    <ConsoleShell title="帮助中心">
      <div className="grid min-h-full grid-cols-1 bg-slate-50 lg:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="border-b border-slate-200 bg-white p-4 lg:border-b-0 lg:border-r">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
            <BookOpen className="h-4 w-4" />
            帮助中心
          </div>
          <label className="mt-4 flex h-9 items-center gap-2 rounded-md border border-slate-200 bg-slate-50 px-2 text-xs">
            <Search className="h-3.5 w-3.5 text-slate-400" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索 专家、清单、留存..."
              className="min-w-0 flex-1 bg-transparent outline-none"
            />
          </label>
          <div className="mt-4 space-y-4">
            {(index.data?.categories ?? []).map((category) => {
              const docs = filteredDocs.filter((doc) => doc.category === category);
              if (!docs.length) return null;
              return (
                <div key={category}>
                  <div className="mb-1 text-[11px] font-semibold uppercase text-slate-400">{category}</div>
                  <div className="space-y-1">
                    {docs.map((doc) => (
                      <button
                        key={doc.id}
                        type="button"
                        onClick={() => {
                          setActiveId(doc.id);
                          setFeedback(null);
                        }}
                        className={cn(
                          "flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-xs",
                          doc.id === activeDoc?.id
                            ? "bg-slate-900 text-white"
                            : "text-slate-600 hover:bg-slate-100 hover:text-slate-950",
                        )}
                      >
                        <span className="truncate">{doc.title}</span>
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </aside>
        <main className="min-w-0 p-4">
          <Card className="mx-auto max-w-5xl">
            <CardHeader>
              <div>
                <div className="text-sm font-semibold text-slate-950">{activeDoc?.title ?? "帮助文档"}</div>
                <div className="mt-1 flex flex-wrap gap-1">
                  {(activeDoc?.keywords ?? []).slice(0, 5).map((keyword) => (
                    <Badge key={keyword} tone="neutral">{keyword}</Badge>
                  ))}
                </div>
              </div>
            </CardHeader>
            <div className="p-5">
              {content.isLoading ? (
                <div className="space-y-3">
                  <Skeleton className="h-5 w-64" />
                  <Skeleton className="h-4 w-full" />
                  <Skeleton className="h-4 w-5/6" />
                  <Skeleton className="h-32 w-full" />
                </div>
              ) : (
                <MarkdownContent source={content.data ?? ""} />
              )}
              <div className="mt-8 rounded-lg border border-slate-200 bg-slate-50 p-3">
                <div className="text-xs font-semibold text-slate-900">对这篇有帮助吗？</div>
                <div className="mt-2 flex gap-2">
                  <Button
                    variant={feedback === "yes" ? "primary" : "secondary"}
                    onClick={() => setFeedback("yes")}
                  >
                    {feedback === "yes" ? <Check className="h-3.5 w-3.5" /> : null}
                    有帮助
                  </Button>
                  <Button
                    variant={feedback === "no" ? "primary" : "secondary"}
                    onClick={() => setFeedback("no")}
                  >
                    {feedback === "no" ? <Check className="h-3.5 w-3.5" /> : null}
                    需要改进
                  </Button>
                </div>
              </div>
            </div>
          </Card>
        </main>
      </div>
    </ConsoleShell>
  );
}

async function fetchHelpIndex(): Promise<HelpIndex> {
  const response = await fetch("/help/index.json");
  if (!response.ok) throw new Error("帮助索引不可用");
  return response.json();
}

async function fetchHelpDoc(path: string): Promise<string> {
  const response = await fetch(path);
  if (!response.ok) throw new Error("帮助文档不可用");
  return response.text();
}
