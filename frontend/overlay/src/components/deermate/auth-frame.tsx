"use client";
import Link from "next/link";

import { useI18n } from "@/core/i18n/hooks";

import { DeerMark } from "./brand";
import { dmCopy } from "./i18n/copy";
import { Button, Card } from "./ui";
export function AuthFrame({ children }: { children: React.ReactNode }) {
  const { locale } = useI18n();
  return (
    <main data-testid="auth" className="dm-auth">
      <Card data-testid="auth-card" className="dm-auth-card grid gap-6">
        <Link data-testid="wordmark" href="/workspace" className="dm-wordmark">
          <DeerMark />
          DeerMate
        </Link>
        {children}
        <Button asChild variant="ghost">
          <Link href="/docs">{dmCopy(locale === "zh-CN", "common.docs")}</Link>
        </Button>
      </Card>
    </main>
  );
}
