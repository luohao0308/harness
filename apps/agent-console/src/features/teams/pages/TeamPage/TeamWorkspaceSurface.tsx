import { GitFork, PanelRightClose, PanelRightOpen } from "lucide-react";
import { useMemo, useState, type ComponentProps, type ReactNode } from "react";
import { Group, Panel, Separator, usePanelRef } from "react-resizable-panels";

import { cn } from "../../../../lib/utils";

import { DesktopTeamInspector } from "./DesktopTeamInspector";
import { DesktopTeamTaskGraph } from "./DesktopTeamTaskGraph";
import { DesktopTeamOverview } from "./DesktopTeamOverview";
import type { TeamWorkspaceView } from "./DesktopTeamViewSwitch";
import { displayAgentStatus } from "./teamState";
import { TeamColumnList } from "./TeamColumnList";

type TeamColumnListProps = ComponentProps<typeof TeamColumnList>;

function DesktopSplitView({
  mode,
  renderPrimary,
  secondary,
  secondaryLabel,
  text,
}: {
  mode: "collaboration" | "graph";
  renderPrimary: (toggleSecondary: () => void) => ReactNode;
  secondary: ReactNode;
  secondaryLabel: string;
  text: TeamColumnListProps["text"];
}) {
  const secondaryPanelRef = usePanelRef();
  const [collapsed, setCollapsed] = useState(false);
  const primarySize = mode === "collaboration" ? "80%" : "56%";
  const secondarySize = mode === "collaboration" ? "20%" : "44%";
  const toggleLabel = collapsed
    ? text(`展开${secondaryLabel}`, `Expand ${secondaryLabel}`)
    : text(`收起${secondaryLabel}`, `Collapse ${secondaryLabel}`);

  const toggleSecondary = () => {
    const panelCollapsed = secondaryPanelRef.current?.isCollapsed() ?? collapsed;
    if (panelCollapsed) {
      secondaryPanelRef.current?.expand();
    } else {
      secondaryPanelRef.current?.collapse();
    }
    setCollapsed(!panelCollapsed);
  };

  return (
    <div className="relative h-full min-h-0 w-full" data-testid={`desktop-team-${mode}-view`}>
      <Group orientation="horizontal" className="h-full min-h-0">
        <Panel id={`${mode}-conversation`} defaultSize={primarySize} minSize="480px">
          <div className="flex h-full min-h-0">{renderPrimary(toggleSecondary)}</div>
        </Panel>
        <Separator className="relative z-20 w-px bg-slate-100 transition-colors hover:bg-blue-400 focus-visible:bg-blue-500 focus-visible:outline-none">
          <button
            type="button"
            aria-label={toggleLabel}
            title={toggleLabel}
            onClick={(event) => {
              event.stopPropagation();
              toggleSecondary();
            }}
            className={cn(
              "absolute left-1/2 top-1/2 flex h-8 w-8 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-500 transition-colors hover:border-blue-300 hover:text-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500",
              collapsed ? "translate-x-1" : "",
            )}
          >
            {collapsed ? <PanelRightOpen aria-hidden="true" className="h-4 w-4" /> : <PanelRightClose aria-hidden="true" className="h-4 w-4" />}
          </button>
        </Separator>
        <Panel
          id={`${mode}-secondary`}
          panelRef={secondaryPanelRef}
          defaultSize={secondarySize}
          minSize={mode === "collaboration" ? "220px" : "280px"}
          maxSize={mode === "collaboration" ? "26%" : "52%"}
          collapsible
          collapsedSize="0%"
          onResize={(size) => setCollapsed(size.inPixels === 0)}
        >
          <div className="h-full min-h-0">{secondary}</div>
        </Panel>
      </Group>
    </div>
  );
}

export function TeamWorkspaceSurface({
  desktopEnabled,
  view,
  activeSlotId,
  focusSlotId,
  onSelectAgent,
  onEnterFocus,
  onExitFocus,
  focusPanel,
  onFocusPanelChange,
  columnListProps,
}: {
  desktopEnabled: boolean;
  view: TeamWorkspaceView;
  activeSlotId: string;
  focusSlotId: string | null;
  onSelectAgent: (slotId: string) => void;
  onEnterFocus: (slotId: string) => void;
  onExitFocus: () => void;
  focusPanel: "inspector" | "graph";
  onFocusPanelChange: (panel: "inspector" | "graph") => void;
  columnListProps: TeamColumnListProps;
}) {
  const {
    activeTeam,
    orderedAgents,
    selectedAgent,
    tasks,
    messages,
    pendingWakeSlotIds,
    streamingWakes,
    settledWakeCutoffs,
    text,
  } = columnListProps;
  const statusBySlotId = useMemo(
    () =>
      new Map(
        orderedAgents.map((agent) => [
          agent.slot_id,
          displayAgentStatus(agent, pendingWakeSlotIds, streamingWakes, settledWakeCutoffs),
        ]),
      ),
    [orderedAgents, pendingWakeSlotIds, settledWakeCutoffs, streamingWakes],
  );

  if (!desktopEnabled || view === "columns") {
    return <TeamColumnList {...columnListProps} />;
  }

  const selectAgent = (slotId: string) => {
    onSelectAgent(slotId);
    if (view === "collaboration" && focusSlotId === null) onEnterFocus(slotId);
  };

  if (view === "collaboration" && focusSlotId === null) {
    return (
      <DesktopTeamOverview
        team={activeTeam}
        agents={orderedAgents}
        tasks={tasks}
        messages={messages}
        activeSlotId={activeSlotId}
        pendingWakeSlotIds={pendingWakeSlotIds}
        streamingWakes={streamingWakes}
        settledWakeCutoffs={settledWakeCutoffs}
        text={text}
        onSelectAgent={selectAgent}
      />
    );
  }

  const singleConversation = (
    supplement?: ReactNode,
    fullscreenAction: ((slotId: string) => void) | null = null,
  ) => (
    <TeamColumnList
      {...columnListProps}
      fullscreenSlotId={null}
      isNarrowColumns
      columnOverflow={{ left: false, right: false }}
      selectedColumnSupplement={supplement}
      hideSelectedTaskSteps
      selectedColumnFullscreenAction={fullscreenAction}
    />
  );

  const focusHeader = (
    <div className="mx-auto flex w-full max-w-[760px] items-center justify-between border-b border-slate-100 px-1 py-2 text-xs text-slate-600">
      <span>{text("专注对话", "Focus conversation")}</span>
      <div className="flex items-center gap-1">
        {!columnListProps.isNarrowColumns ? (
          <button
            type="button"
            aria-pressed={focusPanel === "graph"}
            onClick={() => onFocusPanelChange(focusPanel === "graph" ? "inspector" : "graph")}
            className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-slate-500 hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            <GitFork aria-hidden="true" className="h-3 w-3" />
            {focusPanel === "graph" ? text("返回检查器", "Back to inspector") : text("查看任务图", "View task graph")}
          </button>
        ) : null}
        <button
          type="button"
          onClick={onExitFocus}
          className="rounded-md px-2 py-1 text-[11px] text-slate-500 hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
        >
          {text("返回团队概览", "Back to team overview")}
        </button>
      </div>
    </div>
  );

  if (columnListProps.isNarrowColumns) {
    if (view === "graph") {
      return (
        <DesktopTeamTaskGraph
          team={activeTeam}
          agents={orderedAgents}
          tasks={tasks}
          activeSlotId={activeSlotId}
          text={text}
          onSelectAgent={onSelectAgent}
        />
      );
    }
    return singleConversation(focusHeader);
  }

  if (view === "graph") {
    return (
      <DesktopSplitView
        mode="graph"
        renderPrimary={(toggleSecondary) => singleConversation(undefined, () => toggleSecondary())}
        secondary={
          <DesktopTeamTaskGraph
            team={activeTeam}
            agents={orderedAgents}
            tasks={tasks}
            activeSlotId={activeSlotId}
            text={text}
            onSelectAgent={onSelectAgent}
          />
        }
        secondaryLabel={text("任务图", "task graph")}
        text={text}
      />
    );
  }

  return (
    <DesktopSplitView
      mode="collaboration"
      renderPrimary={(toggleSecondary) => singleConversation(focusHeader, () => toggleSecondary())}
      secondary={
        focusPanel === "graph" ? (
          <DesktopTeamTaskGraph
            team={activeTeam}
            agents={orderedAgents}
            tasks={tasks}
            activeSlotId={activeSlotId}
            text={text}
            onSelectAgent={onSelectAgent}
          />
        ) : (
          <DesktopTeamInspector
            team={activeTeam}
            agents={orderedAgents}
            selectedAgent={selectedAgent}
            tasks={tasks}
            messages={messages}
            status={selectedAgent ? statusBySlotId.get(selectedAgent.slot_id) ?? selectedAgent.status : null}
            text={text}
            onSelectAgent={onSelectAgent}
          />
        )
      }
      secondaryLabel={focusPanel === "graph" ? text("任务图", "task graph") : text("团队检查器", "team inspector")}
      text={text}
    />
  );
}
