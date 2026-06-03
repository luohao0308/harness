import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Trash2, UserPlus, Users } from "lucide-react";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { EmptyState } from "../../../components/ui/EmptyState";
import { Input } from "../../../components/ui/input";
import { MenuSelect } from "../../../components/ui/menu-select";
import { SkeletonTable } from "../../../components/ui/Skeleton";
import { Table, Td, Th } from "../../../components/ui/table";
import { formatShortDate } from "../../../lib/utils";
import {
  inviteOrganizationUser,
  listOrganizationUsers,
  removeOrganizationUser,
  updateOrganizationUserRole,
  type UserMember,
} from "../../tasks/api";

const roleOptions = [
  { value: "admin", label: "admin", description: "组织管理" },
  { value: "member", label: "member", description: "运行与创建" },
  { value: "viewer", label: "viewer", description: "只读访问" },
];

export function UserManagementPage() {
  const queryClient = useQueryClient();
  const users = useQuery({
    queryKey: ["settings", "users"],
    queryFn: listOrganizationUsers,
  });
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<"admin" | "member" | "viewer">("member");
  const [message, setMessage] = useState("");

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["settings", "users"] });
  const invite = useMutation({
    mutationFn: inviteOrganizationUser,
    onSuccess: () => {
      setEmail("");
      setName("");
      setRole("member");
      setMessage("");
      void invalidate();
    },
    onError: (error) => setMessage(error instanceof Error ? error.message : "邀请失败"),
  });
  const updateRole = useMutation({
    mutationFn: ({ userId, nextRole }: { userId: string; nextRole: "admin" | "member" | "viewer" }) =>
      updateOrganizationUserRole(userId, nextRole),
    onSuccess: () => void invalidate(),
  });
  const remove = useMutation({
    mutationFn: removeOrganizationUser,
    onSuccess: () => void invalidate(),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    setMessage("");
    invite.mutate({ email, name: name || null, role });
  }

  return (
    <ConsoleShell title="用户管理">
      <div className="space-y-4 p-4">
        <section className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_360px]">
          <Card>
            <CardHeader>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <Users className="h-4 w-4" />
                成员
              </div>
              <Badge tone="neutral">{users.data?.length ?? 0}</Badge>
            </CardHeader>
            {users.isLoading ? (
              <SkeletonTable rows={6} columns={5} />
            ) : users.data?.length ? (
              <Table>
                <thead className="bg-slate-50 text-slate-500">
                  <tr>
                    <Th>用户</Th>
                    <Th>角色</Th>
                    <Th>状态</Th>
                    <Th>加入</Th>
                    <Th className="text-right">操作</Th>
                  </tr>
                </thead>
                <tbody>
                  {users.data.map((member) => (
                    <UserRow
                      key={member.membership_id}
                      member={member}
                      pendingRole={updateRole.isPending}
                      pendingRemove={remove.isPending}
                      onRoleChange={(nextRole) => updateRole.mutate({ userId: member.user_id, nextRole })}
                      onRemove={() => remove.mutate(member.user_id)}
                    />
                  ))}
                </tbody>
              </Table>
            ) : (
              <div className="p-3">
                <EmptyState
                  icon={<Users className="h-5 w-5" />}
                  title="暂无成员"
                  description="邀请成员后会显示在这里。"
                />
              </div>
            )}
          </Card>

          <Card className="p-3">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-900">
              <UserPlus className="h-4 w-4" />
              邀请成员
            </div>
            <form className="space-y-3" onSubmit={submit}>
              <label className="block text-xs font-medium text-slate-600">
                邮箱
                <Input
                  className="mt-1 w-full"
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  required
                />
              </label>
              <label className="block text-xs font-medium text-slate-600">
                姓名
                <Input
                  className="mt-1 w-full"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                />
              </label>
              <MenuSelect
                ariaLabel="邀请角色"
                value={role}
                options={roleOptions}
                onChange={(value) => setRole(value as typeof role)}
                size="compact"
                buttonClassName="rounded-md shadow-none"
              />
              {message ? <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">{message}</div> : null}
              <Button type="submit" variant="primary" className="w-full" disabled={invite.isPending}>
                {invite.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <UserPlus className="h-3.5 w-3.5" />}
                邀请
              </Button>
            </form>
          </Card>
        </section>
      </div>
    </ConsoleShell>
  );
}

function UserRow({
  member,
  onRemove,
  onRoleChange,
  pendingRemove,
  pendingRole,
}: {
  member: UserMember;
  onRemove: () => void;
  onRoleChange: (role: "admin" | "member" | "viewer") => void;
  pendingRemove: boolean;
  pendingRole: boolean;
}) {
  const role = member.role === "owner" ? "admin" : (member.role as "admin" | "member" | "viewer");
  const immutableOwner = member.role === "owner";
  return (
    <tr className="border-t border-slate-100">
      <Td>
        <div className="font-medium text-slate-900">{member.name}</div>
        <div className="font-mono text-[11px] text-slate-500">{member.email}</div>
      </Td>
      <Td className="w-48">
        {immutableOwner ? (
          <Badge tone="success">owner</Badge>
        ) : (
          <MenuSelect
            ariaLabel={`${member.email} 角色`}
            value={role}
            options={roleOptions}
            onChange={(value) => onRoleChange(value as "admin" | "member" | "viewer")}
            size="compact"
            disabled={pendingRole}
            buttonClassName="rounded-md shadow-none"
          />
        )}
      </Td>
      <Td><Badge tone={member.status === "active" ? "success" : "warning"}>{member.status}</Badge></Td>
      <Td className="font-mono text-slate-500">{formatShortDate(member.accepted_at ?? member.invited_at)}</Td>
      <Td className="text-right">
        <Button variant="ghost" disabled={immutableOwner || pendingRemove} onClick={onRemove} title="移除成员">
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </Td>
    </tr>
  );
}
