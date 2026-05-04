import { Badge, Dot, statusTone } from "../../../components/ui/badge";

export function TaskStatusBadge({ status }: { status: string }) {
  const tone = statusTone(status);
  return (
    <Badge tone={tone}>
      <Dot tone={tone} />
      {status}
    </Badge>
  );
}
