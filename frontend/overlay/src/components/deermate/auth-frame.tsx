"use client";

import { ArrowUpRight, ShieldCheck } from "lucide-react";
import { useI18n } from "@/core/i18n/hooks";
import { BrandMotion, DeerMark } from "./brand";

export function AuthFrame({ children }: { children: React.ReactNode }) {
  const { locale } = useI18n();
  const zh = locale === "zh-CN";
  return (
    <div className="dm-auth">
      <aside className="dm-auth-story">
        <div className="dm-wordmark">
          <DeerMark />
          DeerMate<span>PRIVATE BY DESIGN</span>
        </div>
        <div className="dm-auth-message">
          <BrandMotion />
          <p className="dm-eyebrow">YOUR AGENTS. YOUR MACHINES.</p>
          <h1>
            {zh ? (
              <>
                目标交给我。
                <br />
                时间留给你。
              </>
            ) : (
              <>
                A little less busy.
                <br />A lot more done.
              </>
            )}
          </h1>
          <p>
            {zh
              ? "一个私人秘书，连接你的 Agent，在自己的机器上完成工作。"
              : "One personal secretary. Your specialist agents. Work done on your own machines."}
          </p>
          <div className="dm-auth-route">
            <span>DeerMate</span>
            <ArrowUpRight size={15} />
            <span>Codex Worker</span>
          </div>
        </div>
        <footer>
          <ShieldCheck size={15} />
          {zh ? "由你部署，由你掌控。" : "Self-hosted. Yours to control."}
        </footer>
      </aside>
      <main className="dm-auth-form">{children}</main>
    </div>
  );
}
