"use client";
import { MoreHorizontal } from "lucide-react";

import {
  Card,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  Heading,
  IconButton,
  StatusBadge,
} from "../ui";
export function FocusRow({
  title,
  domain,
  status,
  meta,
  action,
  menu,
  menuLabel,
}: {
  title: string;
  domain: string;
  status: string;
  meta: React.ReactNode;
  action: React.ReactNode;
  menu: { label: string; action: () => void }[];
  menuLabel: string;
}) {
  return (
    <Card
      as="li"
      variant="compact"
      data-testid="focus-card"
      className="flex min-w-0 items-center gap-3 py-2"
    >
      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <StatusBadge domain={domain} status={status} />
          <Heading level={3} className="min-w-0 flex-1 truncate">
            {title}
          </Heading>
        </div>
        <div className="mt-1">{meta}</div>
      </div>
      <div className="flex shrink-0 items-center gap-1">
        {action}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <IconButton
              label={menuLabel}
              icon={<MoreHorizontal className="size-4" />}
            />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {menu.map((item) => (
              <DropdownMenuItem key={item.label} onSelect={item.action}>
                {item.label}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </Card>
  );
}
