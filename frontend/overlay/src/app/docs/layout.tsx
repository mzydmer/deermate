import type { Metadata } from "next";
import { DocsShell } from "@/components/deermate/product-docs";

export const metadata: Metadata = {
  title: { default: "产品文档 · DeerMate", template: "%s · DeerMate 文档" },
  description: "DeerMate 产品使用指南、系统技术方案与变更日志。",
};

export default function DocsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <DocsShell>{children}</DocsShell>;
}
