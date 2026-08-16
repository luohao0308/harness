import { useCallback, useEffect, useRef, type Dispatch, type SetStateAction } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  cancelWakeTeamAgent,
  streamTeamEvents,
  streamWakeTeamAgent,
  wakeTeamAgent,
  type Team,
  type TeamAgent,
  type TeamWakeStreamEvent,
} from "../../../tasks/api";

import {
  appendSessionMessageToAgent,
  applyTeamEventToTeam,
  applyTeamEventToTeamPage,
  completedWakeSlotIdFromTeamEvent,
  isRecord,
  isTeamAgent,
  mergeTeamAgent,
  settledWakeAgent,
  timestampMs,
} from "./teamState";
import type { SettledWakeCutoffs, StreamingWake, TeamPageEnvelope } from "./types";

type UseTeamEventsAndWakeArgs = {
  teamId: string;
  streamReadyTeamId?: string;
  setActiveSlotId: Dispatch<SetStateAction<string>>;
  setSettledWakeCutoffs: Dispatch<SetStateAction<SettledWakeCutoffs>>;
  setPendingWakeSlotIds: Dispatch<SetStateAction<string[]>>;
  setStreamingWakes: Dispatch<SetStateAction<StreamingWake[]>>;
};

export function useTeamEventsAndWake({
  teamId,
  streamReadyTeamId,
  setActiveSlotId,
  setSettledWakeCutoffs,
  setPendingWakeSlotIds,
  setStreamingWakes,
}: UseTeamEventsAndWakeArgs) {
  const queryClient = useQueryClient();
  const wakeControllersRef = useRef<Record<string, AbortController>>({});
  const userCancelledWakeSlotIdsRef = useRef<Set<string>>(new Set());
  const failedWakeStreamSlotIdsRef = useRef<Set<string>>(new Set());
  const terminalWakeSlotIdsRef = useRef<Set<string>>(new Set());
  const cancelledWakeCutoffsRef = useRef<Record<string, number>>({});
  const followUpWakeRef = useRef<(slotIds: string[]) => void>(() => undefined);

  const isCancelledWakeEvent = useCallback((slotId: string | null | undefined, updatedAt?: string | null) => {
    if (!slotId) return false;
    const cutoff = cancelledWakeCutoffsRef.current[slotId];
    if (!cutoff) return false;
    const updatedAtMs = timestampMs(updatedAt ?? undefined);
    return updatedAtMs === null || updatedAtMs <= cutoff;
  }, []);

  useEffect(() => {
    if (!teamId || !streamReadyTeamId) return;
    const controller = new AbortController();
    void streamTeamEvents(
      teamId,
      (event) => {
        let applied = false;
        queryClient.setQueryData<Team>(["teams", teamId], (current) => {
          if (!current) return current;
          const eventAgent = event.payload_json.agent;
          if (
            isTeamAgent(eventAgent) &&
            isCancelledWakeEvent(eventAgent.slot_id, eventAgent.updated_at)
          ) {
            applied = true;
            return current;
          }
          const next = applyTeamEventToTeam(current, event);
          if (!next) return current;
          applied = true;
          return next;
        });
        queryClient.setQueryData<TeamPageEnvelope>(["teams"], (current) => {
          const eventAgent = event.payload_json.agent;
          if (
            isTeamAgent(eventAgent) &&
            isCancelledWakeEvent(eventAgent.slot_id, eventAgent.updated_at)
          ) {
            return current;
          }
          const next = applyTeamEventToTeamPage(current, event);
          return next ?? current;
        });
        if (!applied) {
          void queryClient.invalidateQueries({ queryKey: ["teams", teamId] });
          void queryClient.invalidateQueries({ queryKey: ["teams"] });
        }
        if (event.event_type === "TEAM_AGENT_SPAWNED") {
          const agent = event.payload_json.agent;
          if (isTeamAgent(agent)) {
            setActiveSlotId(agent.slot_id);
          }
        }
        const completedWakeSlotId = completedWakeSlotIdFromTeamEvent(event);
        if (completedWakeSlotId) {
          terminalWakeSlotIdsRef.current.add(completedWakeSlotId);
          wakeControllersRef.current[completedWakeSlotId]?.abort();
          const cutoffMs = timestampMs(event.created_at) ?? Date.now();
          setSettledWakeCutoffs((current) => ({
            ...current,
            [completedWakeSlotId]: Math.max(current[completedWakeSlotId] ?? 0, cutoffMs),
          }));
          setPendingWakeSlotIds((current) =>
            current.filter((candidate) => candidate !== completedWakeSlotId),
          );
          setStreamingWakes((current) => current.filter((wake) => wake.slotId !== completedWakeSlotId));
        }
      },
      controller.signal,
    ).catch(() => undefined);
    return () => controller.abort();
  }, [
    queryClient,
    setActiveSlotId,
    setPendingWakeSlotIds,
    setSettledWakeCutoffs,
    setStreamingWakes,
    isCancelledWakeEvent,
    streamReadyTeamId,
    teamId,
  ]);

  const applyWakeStreamEvent = useCallback(
    (event: TeamWakeStreamEvent) => {
      if (event.type === "delta") {
        if (isCancelledWakeEvent(event.slot_id)) return;
        setStreamingWakes((current) => {
          const existing = current.find((wake) => wake.slotId === event.slot_id);
          if (!existing) {
            return [...current, { slotId: event.slot_id, content: event.content }];
          }
          return current.map((wake) =>
            wake.slotId === event.slot_id
              ? { ...wake, content: `${wake.content}${event.content}` }
              : wake,
          );
        });
        return;
      }
      if (event.type === "status" || event.type === "done") {
        if (isCancelledWakeEvent(event.agent.slot_id, event.agent.updated_at)) return;
        queryClient.setQueryData<Team>(["teams", teamId], (current) => {
          if (!current) return current;
          const incomingAgent = event.type === "done" ? settledWakeAgent(event.agent) : event.agent;
          const agents = event.type === "done" && event.message
            ? appendSessionMessageToAgent(current, incomingAgent.slot_id, event.message)
            : current.agents;
          return {
            ...current,
            agents: mergeTeamAgent(agents, incomingAgent),
          };
        });
      }
      if (event.type === "done") {
        terminalWakeSlotIdsRef.current.add(event.agent.slot_id);
        failedWakeStreamSlotIdsRef.current.delete(event.agent.slot_id);
        setSettledWakeCutoffs((current) => ({
          ...current,
          [event.agent.slot_id]: Math.max(
            current[event.agent.slot_id] ?? 0,
            timestampMs(event.agent.updated_at) ?? Date.now(),
          ),
        }));
        setStreamingWakes((current) => current.filter((wake) => wake.slotId !== event.agent.slot_id));
        setPendingWakeSlotIds((current) => current.filter((candidate) => candidate !== event.agent.slot_id));
        if (event.follow_up_slot_ids?.length) {
          followUpWakeRef.current(event.follow_up_slot_ids);
        }
        void queryClient.invalidateQueries({ queryKey: ["teams", teamId] });
        void queryClient.invalidateQueries({ queryKey: ["teams"] });
      }
      if (event.type === "error") {
        const slotId = event.agent?.slot_id ?? event.slot_id;
        if (!slotId) return;
        if (isCancelledWakeEvent(slotId, event.agent?.updated_at)) return;
        terminalWakeSlotIdsRef.current.add(slotId);
        failedWakeStreamSlotIdsRef.current.add(slotId);
        setPendingWakeSlotIds((current) => current.filter((candidate) => candidate !== slotId));
        setStreamingWakes((current) => {
          const existing = current.find((wake) => wake.slotId === slotId);
          const happenedAt = event.agent?.updated_at ?? undefined;
          if (!existing) return [...current, { slotId, content: "", error: event.message, happenedAt }];
          return current.map((wake) =>
            wake.slotId === slotId ? { ...wake, error: event.message, happenedAt } : wake,
          );
        });
        if (event.agent) {
          queryClient.setQueryData<Team>(["teams", teamId], (current) => {
            if (!current) return current;
            return {
              ...current,
              agents: mergeTeamAgent(current.agents, {
                ...event.agent!,
                metadata_json: {
                  ...event.agent!.metadata_json,
                  wake: {
                    ...(isRecord(event.agent!.metadata_json?.wake) ? event.agent!.metadata_json.wake : {}),
                    in_progress: false,
                  },
                },
              }),
            };
          });
        }
      }
    },
    [isCancelledWakeEvent, queryClient, setPendingWakeSlotIds, setSettledWakeCutoffs, setStreamingWakes, teamId],
  );

  const settleWakeLocally = useCallback(
    (slotId: string, agentPatch?: TeamAgent) => {
      const nowMs = timestampMs(agentPatch?.updated_at) ?? Date.now();
      setSettledWakeCutoffs((current) => ({
        ...current,
        [slotId]: Math.max(current[slotId] ?? 0, nowMs),
      }));
      setPendingWakeSlotIds((current) => current.filter((candidate) => candidate !== slotId));
      setStreamingWakes((current) => current.filter((wake) => wake.slotId !== slotId || wake.error));
      queryClient.setQueryData<Team>(["teams", teamId], (current) => {
        if (!current) return current;
        const existing = current.agents.find((agent) => agent.slot_id === slotId);
        const settledAgent = agentPatch ?? existing;
        if (!settledAgent) return current;
        return {
          ...current,
          agents: mergeTeamAgent(current.agents, {
            ...settledAgent,
            status: "idle",
            metadata_json: {
              ...settledAgent.metadata_json,
              wake: {
                ...(isRecord(settledAgent.metadata_json?.wake) ? settledAgent.metadata_json.wake : {}),
                in_progress: false,
              },
            },
          }),
        };
      });
    },
    [queryClient, setPendingWakeSlotIds, setSettledWakeCutoffs, setStreamingWakes, teamId],
  );

  const triggerWake = useCallback(
    (slotIds: string[]) => {
      const uniqueSlotIds = [...new Set(slotIds)].filter(Boolean);
      for (const slotId of uniqueSlotIds) {
        if (wakeControllersRef.current[slotId]) continue;
        delete cancelledWakeCutoffsRef.current[slotId];
        failedWakeStreamSlotIdsRef.current.delete(slotId);
        terminalWakeSlotIdsRef.current.delete(slotId);
        setSettledWakeCutoffs((current) => {
          if (!(slotId in current)) return current;
          const next = { ...current };
          delete next[slotId];
          return next;
        });
        const controller = new AbortController();
        wakeControllersRef.current[slotId] = controller;
        setPendingWakeSlotIds((current) => (current.includes(slotId) ? current : [...current, slotId]));
        setStreamingWakes((current) =>
          current.some((wake) => wake.slotId === slotId)
            ? current
            : [...current, { slotId, content: "" }],
        );
        streamWakeTeamAgent(teamId, slotId, applyWakeStreamEvent, controller.signal)
          .then(() => {
            if (!failedWakeStreamSlotIdsRef.current.has(slotId)) {
              settleWakeLocally(slotId);
            }
            void queryClient.invalidateQueries({ queryKey: ["teams", teamId] });
          })
          .catch(() => {
            if (terminalWakeSlotIdsRef.current.has(slotId)) return;
            if (controller.signal.aborted) {
              if (userCancelledWakeSlotIdsRef.current.has(slotId)) {
                settleWakeLocally(slotId);
              }
              return;
            }
            return wakeTeamAgent(teamId, slotId).then(() => {
              void queryClient.invalidateQueries({ queryKey: ["teams", teamId] });
            }).catch(() => undefined);
          })
          .finally(() => {
            userCancelledWakeSlotIdsRef.current.delete(slotId);
            failedWakeStreamSlotIdsRef.current.delete(slotId);
            terminalWakeSlotIdsRef.current.delete(slotId);
            delete wakeControllersRef.current[slotId];
            setPendingWakeSlotIds((current) => current.filter((candidate) => candidate !== slotId));
            setStreamingWakes((current) => current.filter((wake) => wake.slotId !== slotId || wake.error));
          });
      }
    },
    [
      applyWakeStreamEvent,
      queryClient,
      setPendingWakeSlotIds,
      setSettledWakeCutoffs,
      setStreamingWakes,
      settleWakeLocally,
      teamId,
    ],
  );

  useEffect(() => {
    followUpWakeRef.current = triggerWake;
  }, [triggerWake]);

  const stopWake = useCallback(
    (slotId: string) => {
      userCancelledWakeSlotIdsRef.current.add(slotId);
      cancelledWakeCutoffsRef.current[slotId] = Date.now();
      wakeControllersRef.current[slotId]?.abort();
      settleWakeLocally(slotId);
      cancelWakeTeamAgent(teamId, slotId)
        .then((agent) => {
          settleWakeLocally(slotId, agent);
          void queryClient.invalidateQueries({ queryKey: ["teams", teamId] });
        })
        .catch(() => undefined);
    },
    [queryClient, settleWakeLocally, teamId],
  );

  useEffect(
    () => () => {
      for (const controller of Object.values(wakeControllersRef.current)) {
        controller.abort();
      }
    },
    [],
  );

  return { triggerWake, stopWake };
}
