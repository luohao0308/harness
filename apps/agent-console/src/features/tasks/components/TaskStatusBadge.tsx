import { Badge, Dot, statusTone } from "../../../components/ui/badge";
import { statusLabel } from "../../../lib/labels";

export function TaskStatusBadge({ status }: { status: string }) {
  const tone = statusTone(status);
  return (
    <Badge tone={tone}>
      <Dot tone={tone} />
      {statusLabel(status)}
    </Badge>
  );
}
