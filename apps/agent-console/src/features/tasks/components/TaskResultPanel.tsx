import { AlertCircle } from "lucide-react";

import type { Task } from "../api";
import { Card, CardHeader } from "../../../components/ui/card";
import { Table, Td, Th } from "../../../components/ui/table";

export function TaskResultPanel({ task }: { task: Task }) {
  const rows = [
    ["plan.json", "json", "Execution plan", task.status === "COMPLETED" ? "ready" : "pending"],
    ["events.jsonl", "jsonl", "Event stream export", "ready"],
    ["result.md", "markdown", "Final task result", task.completed_at ? "ready" : "pending"],
  ];
  return (
    <Card>
      <CardHeader>
        <div className="text-[11px] tracking-widest text-slate-500">TASK RESULT · ARTIFACTS</div>
        <span className="inline-flex items-center gap-1 text-[11px] text-slate-500">
          <AlertCircle className="h-3 w-3" /> {task.status.toLowerCase()}
        </span>
      </CardHeader>
      <Table>
        <thead className="bg-slate-50/40 text-slate-500">
          <tr>
            <Th>Name</Th>
            <Th>Kind</Th>
            <Th>Description</Th>
            <Th>Status</Th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row[0]} className="border-t border-slate-100">
              <Td className="font-mono text-slate-800">{row[0]}</Td>
              <Td className="text-slate-600">{row[1]}</Td>
              <Td className="text-slate-600">{row[2]}</Td>
              <Td className="font-mono text-slate-500">{row[3]}</Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </Card>
  );
}
