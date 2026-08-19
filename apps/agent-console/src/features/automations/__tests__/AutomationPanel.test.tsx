import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AutomationPanel } from "../components/AutomationPanel";

function response(payload: unknown, status = 200) {
  return new Response(status === 204 ? null : JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderPanel(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <AutomationPanel agentId="default" agentLabel="默认智能体" />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  Reflect.deleteProperty(window, "desktopApi");
});

describe("AutomationPanel", () => {
  it("creates all trigger types and marks host-bound sources as Desktop only", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(String(input), "http://local").pathname;
      if (path === "/api/agents/default/triggers" && !init?.method) return response({ items: [] });
      if (path === "/api/agents/default/triggers" && init?.method === "POST") {
        const body = JSON.parse(String(init.body)) as { type: string; endpoint_path?: string };
        return response({
          trigger: {
            id: "trigger-1", agent_id: "default", type: body.type, name: "发布自动化",
            config_json: {}, endpoint_path: body.endpoint_path ?? "release-hook", enabled: true,
            created_at: "2026-08-17T12:00:00Z", updated_at: "2026-08-17T12:00:00Z", last_triggered_at: null,
          },
          secret: body.type === "webhook" ? "htrg_once" : null,
        }, 201);
      }
      return response({ detail: path }, 404);
    });

    renderPanel(fetchMock);
    expect(await screen.findByText("暂无自动化")).toBeInTheDocument();
    expect(screen.getByText("文件与 Git 触发仅在 Forge Harness Desktop 本机运行。" )).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "新建自动化" }));
    const dialog = screen.getByRole("dialog", { name: "新建自动化" });
    await user.type(within(dialog).getByLabelText("自动化名称"), "发布自动化");
    await user.click(within(dialog).getByRole("button", { name: /触发类型/ }));
    await user.click(screen.getByRole("option", { name: /定时/ }));
    const intervalInput = within(dialog).getByLabelText("执行间隔（秒）");
    expect(intervalInput).toBeInTheDocument();
    await user.clear(intervalInput);
    await user.type(intervalInput, "4");
    await user.click(within(dialog).getByRole("button", { name: "创建自动化" }));
    expect(within(dialog).getByText("执行间隔必须是 5 到 86400 秒的整数。")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
    await user.click(within(dialog).getByRole("button", { name: /触发类型/ }));
    await user.click(screen.getByRole("option", { name: /文件变更/ }));
    expect(within(dialog).getAllByText("仅本地 Desktop").length).toBeGreaterThan(0);
    expect(within(dialog).getByLabelText("工作区目录")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: /触发类型/ }));
    await user.click(screen.getByRole("option", { name: /Git 提交/ }));
    expect(within(dialog).getByLabelText("Git 仓库目录")).toBeInTheDocument();
  });

  it("submits the validated schedule, file, and git request bodies", async () => {
    const user = userEvent.setup();
    const selectAuthorizedWorkspaceRoot = vi.fn()
      .mockResolvedValueOnce({ authorization: "hwa1_file.signature", label: "project", expiresAt: "2026-08-19T12:05:00Z" })
      .mockResolvedValueOnce({ authorization: "hwa1_git.signature", label: "project", expiresAt: "2026-08-19T12:05:00Z" });
    Object.defineProperty(window, "desktopApi", {
      configurable: true,
      value: { file: { selectAuthorizedWorkspaceRoot } },
    });
    const submitted: Array<Record<string, unknown>> = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(String(input), "http://local").pathname;
      if (path === "/api/agents/default/triggers" && !init?.method) return response({ items: [] });
      if (path === "/api/agents/default/triggers" && init?.method === "POST") {
        const body = JSON.parse(String(init.body)) as Record<string, unknown>;
        submitted.push(body);
        return response({
          trigger: {
            id: `trigger-${submitted.length}`, agent_id: "default", type: body.type,
            name: body.name, config_json: body.config_json, endpoint_path: null, enabled: true,
            created_at: "2026-08-17T12:00:00Z", updated_at: "2026-08-17T12:00:00Z",
            last_triggered_at: null,
          },
          secret: null,
        }, 201);
      }
      return response({ detail: path }, 404);
    });
    renderPanel(fetchMock);
    await screen.findByText("暂无自动化");

    await user.click(screen.getByRole("button", { name: "新建自动化" }));
    let dialog = screen.getByRole("dialog", { name: "新建自动化" });
    await user.type(within(dialog).getByLabelText("自动化名称"), "定时巡检");
    await user.click(within(dialog).getByRole("button", { name: /触发类型/ }));
    await user.click(screen.getByRole("option", { name: /定时/ }));
    await user.clear(within(dialog).getByLabelText("执行间隔（秒）"));
    await user.type(within(dialog).getByLabelText("执行间隔（秒）"), "60");
    await user.click(within(dialog).getByRole("button", { name: "创建自动化" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "新建自动化" })).not.toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "新建自动化" }));
    dialog = screen.getByRole("dialog", { name: "新建自动化" });
    await user.type(within(dialog).getByLabelText("自动化名称"), "文档变更");
    await user.click(within(dialog).getByRole("button", { name: /触发类型/ }));
    await user.click(screen.getByRole("option", { name: /文件变更/ }));
    await user.click(within(dialog).getByTitle("选择工作区目录"));
    expect(within(dialog).getByLabelText("工作区目录")).toHaveValue("project");
    await user.clear(within(dialog).getByLabelText("文件匹配"));
    await user.type(within(dialog).getByLabelText("文件匹配"), "**/*.md");
    await user.click(within(dialog).getByRole("button", { name: "创建自动化" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "新建自动化" })).not.toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "新建自动化" }));
    dialog = screen.getByRole("dialog", { name: "新建自动化" });
    await user.type(within(dialog).getByLabelText("自动化名称"), "主分支更新");
    await user.click(within(dialog).getByRole("button", { name: /触发类型/ }));
    await user.click(screen.getByRole("option", { name: /Git 提交/ }));
    await user.click(within(dialog).getByTitle("选择 Git 仓库目录"));
    expect(within(dialog).getByLabelText("Git 仓库目录")).toHaveValue("project");
    await user.type(within(dialog).getByLabelText("分支（可选）"), "main");
    await user.click(within(dialog).getByRole("button", { name: "创建自动化" }));
    await waitFor(() => expect(submitted).toHaveLength(3));

    expect(submitted).toEqual([
      { type: "schedule", name: "定时巡检", endpoint_path: null, config_json: { max_attempts: 3, interval_seconds: 60 }, enabled: true },
      { type: "file", name: "文档变更", endpoint_path: null, config_json: { max_attempts: 3, workspace_authorization: "hwa1_file.signature", pattern: "**/*.md" }, enabled: true },
      { type: "git", name: "主分支更新", endpoint_path: null, config_json: { max_attempts: 3, workspace_authorization: "hwa1_git.signature", branch: "main" }, enabled: true },
    ]);
    expect(JSON.stringify(submitted)).not.toContain("/tmp/project");
  });

  it("shows a webhook secret once and renders invocation history with Run links", async () => {
    const user = userEvent.setup();
    let created = false;
    const clipboardWrite = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: clipboardWrite } });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(String(input), "http://local").pathname;
      if (path === "/api/agents/default/triggers" && !init?.method) {
        return response({ items: created ? [{
          id: "hook-1", agent_id: "default", type: "webhook", name: "发布 Hook", config_json: {},
          endpoint_path: "release-hook", enabled: true, created_at: "2026-08-17T12:00:00Z",
          updated_at: "2026-08-17T12:00:00Z", last_triggered_at: "2026-08-17T12:05:00Z",
        }] : [] });
      }
      if (path === "/api/agents/default/triggers" && init?.method === "POST") {
        created = true;
        return response({ trigger: {
          id: "hook-1", agent_id: "default", type: "webhook", name: "发布 Hook", config_json: {},
          endpoint_path: "release-hook", enabled: true, created_at: "2026-08-17T12:00:00Z",
          updated_at: "2026-08-17T12:00:00Z", last_triggered_at: null,
        }, secret: "htrg_once" }, 201);
      }
      if (path.endsWith("/hook-1/invocations")) return response({ items: [{
        id: "invoke-1", trigger_id: "hook-1", status: "FAILED", run_id: "run-42", attempt: 2,
        error: "provider timeout", created_at: "2026-08-17T12:05:00Z",
      }] });
      return response({}, 204);
    });

    renderPanel(fetchMock);
    await screen.findByText("暂无自动化");
    await user.click(screen.getByRole("button", { name: "新建自动化" }));
    const dialog = screen.getByRole("dialog", { name: "新建自动化" });
    await user.type(within(dialog).getByLabelText("自动化名称"), "发布 Hook");
    await user.type(within(dialog).getByLabelText("Webhook 路径"), "release-hook");
    await user.click(within(dialog).getByRole("button", { name: "创建自动化" }));

    const secretDialog = await screen.findByRole("dialog", { name: "保存 Webhook 凭据" });
    expect(within(secretDialog).getByText("htrg_once")).toBeInTheDocument();
    expect(within(secretDialog).getByText(/关闭后无法再次查看/)).toBeInTheDocument();
    await user.click(within(secretDialog).getByRole("button", { name: "复制完整 URL" }));
    await user.click(within(secretDialog).getByRole("button", { name: "复制密钥" }));
    expect(clipboardWrite).toHaveBeenCalledTimes(2);
    await user.click(within(secretDialog).getByRole("button", { name: "我已保存" }));

    await user.click(screen.getByRole("button", { name: "新建自动化" }));
    expect(within(screen.getByRole("dialog", { name: "新建自动化" })).getByLabelText("自动化名称")).toHaveValue("");
    await user.click(within(screen.getByRole("dialog", { name: "新建自动化" })).getByRole("button", { name: "取消" }));

    await user.click(await screen.findByRole("button", { name: "查看 发布 Hook 的最近运行" }));
    expect(await screen.findByText("provider timeout")).toBeInTheDocument();
    expect(screen.getByText("第 2 次")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "打开 Run run-42" })).toHaveAttribute("href", "/runs/run-42");
  });

  it("supports refresh, enable changes, soft delete, and permission degradation", async () => {
    const user = userEvent.setup();
    let listCount = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(String(input), "http://local").pathname;
      if (path === "/api/agents/default/triggers" && !init?.method) {
        listCount += 1;
        if (listCount === 1) return response({ detail: "Forbidden" }, 403);
        return response({ items: [{
          id: "schedule-1", agent_id: "default", type: "schedule", name: "定时巡检",
          config_json: { interval_seconds: 300 }, endpoint_path: null, enabled: false,
          created_at: "2026-08-17T12:00:00Z", updated_at: "2026-08-17T12:00:00Z", last_triggered_at: null,
        }] });
      }
      return response({}, init?.method === "DELETE" ? 204 : 200);
    });

    renderPanel(fetchMock);
    expect(await screen.findByText("当前账号无权读取自动化。" )).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "新建自动化" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "重试" }));
    expect(await screen.findByText("定时巡检")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "启用 定时巡检" }));
    await user.click(screen.getByRole("button", { name: "删除 定时巡检" }));
    const firstConfirm = screen.getByRole("dialog", { name: "删除自动化" });
    expect(within(firstConfirm).getByText(/软删除并立即停止新的触发/)).toBeInTheDocument();
    await user.click(within(firstConfirm).getByRole("button", { name: "取消" }));
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(false);
    await user.click(screen.getByRole("button", { name: "删除 定时巡检" }));
    await user.click(within(screen.getByRole("dialog", { name: "删除自动化" })).getByRole("button", { name: "确认删除" }));
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(true);
      expect(fetchMock.mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(true);
    });
  });

  it("reports clipboard failures inside the panel", async () => {
    const user = userEvent.setup();
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: vi.fn().mockRejectedValue(new Error("clipboard unavailable")) } });
    let created = false;
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      if (!init?.method) return response({ items: created ? [] : [] });
      created = true;
      return response({ trigger: {
        id: "hook-copy", agent_id: "default", type: "webhook", name: "Copy Hook", config_json: {},
        endpoint_path: "copy-hook", enabled: true, created_at: "2026-08-17T12:00:00Z",
        updated_at: "2026-08-17T12:00:00Z", last_triggered_at: null,
      }, secret: "htrg_copy" }, 201);
    });

    renderPanel(fetchMock);
    await screen.findByText("暂无自动化");
    await user.click(screen.getByRole("button", { name: "新建自动化" }));
    const createDialog = screen.getByRole("dialog", { name: "新建自动化" });
    await user.type(within(createDialog).getByLabelText("自动化名称"), "Copy Hook");
    await user.click(within(createDialog).getByRole("button", { name: "创建自动化" }));
    const secretDialog = await screen.findByRole("dialog", { name: "保存 Webhook 凭据" });
    await user.click(within(secretDialog).getByRole("button", { name: "复制密钥" }));
    expect(await screen.findByText("clipboard unavailable")).toBeInTheDocument();
  });
});
