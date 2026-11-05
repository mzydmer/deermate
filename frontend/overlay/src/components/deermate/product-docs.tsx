"use client";

import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  Copy,
  FileText,
  FlaskConical,
  Search,
  Sun,
  Moon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import GithubSlugger from "github-slugger";
import rehypeSlug from "rehype-slug";
import {
  SafeStreamdown,
  toStreamdownComponents,
} from "@/core/streamdown/components";
import { DeerMark } from "./brand";
import pages from "./product-docs.generated.json";

const docComponents = toStreamdownComponents({
  a: ({ href, children }) =>
    href?.startsWith("/docs/") ? (
      <Link href={href}>{children}</Link>
    ) : (
      <a href={href}>{children}</a>
    ),
});

export const docGroups = [
  {
    id: "guide",
    title: "使用指南",
    audience: "面向客户",
    description: "从第一项工作开始，了解对话、关注、记忆与设备授权。",
    href: "/docs/guide/overview",
    icon: BookOpen,
  },
  {
    id: "technical",
    title: "技术方案",
    audience: "面向技术与研究读者",
    description: "理解系统架构、持续协作、上下文治理和可复现评估。",
    href: "/docs/technical/architecture",
    icon: FlaskConical,
  },
  {
    id: "changelog",
    title: "变更日志",
    audience: "持续更新",
    description: "了解每次产品变化、启用条件，以及实际交付范围。",
    href: "/docs/changelog",
    icon: FileText,
  },
];

export function DocsShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { resolvedTheme, setTheme } = useTheme();
  const [query, setQuery] = useState("");
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const term = query.trim().toLocaleLowerCase();
  const results = term
    ? pages.filter((page) =>
        `${page.title} ${page.description} ${page.body}`
          .toLocaleLowerCase()
          .includes(term),
      )
    : [];
  const dark = mounted && resolvedTheme === "dark";
  return (
    <div className="dm-docs" lang="zh-CN">
      <a className="dm-docs-skip" href="#docs-main">
        跳到文档正文
      </a>
      <header className="dm-docs-header">
        <Link className="dm-docs-brand" href="/docs">
          <DeerMark />
          <strong>DeerMate</strong>
          <span>产品文档</span>
        </Link>
        <div className="dm-docs-header-actions">
          <button
            type="button"
            onClick={() => setTheme(dark ? "light" : "dark")}
            aria-label={dark ? "切换浅色模式" : "切换深色模式"}
          >
            {dark ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          <Link href="/workspace">
            进入工作台 <ArrowRight size={15} />
          </Link>
        </div>
      </header>
      <div className="dm-docs-layout">
        <aside className="dm-docs-sidebar">
          <div className="dm-docs-search">
            <label htmlFor="docs-search">
              <Search size={15} /> 搜索文档
            </label>
            <input
              id="docs-search"
              type="search"
              placeholder="搜索标题或正文…"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
          {term ? (
            <div className="dm-docs-results">
              <p role="status">
                {results.length
                  ? `找到 ${results.length} 篇文档`
                  : "没有匹配的文档，请尝试其他关键词。"}
              </p>
              <nav aria-label="搜索结果">
                {results.map((page) => (
                  <Link
                    key={page.slug}
                    href={`/docs/${page.slug}`}
                    onClick={() => setQuery("")}
                  >
                    <strong>{page.title}</strong>
                    <small>{page.description}</small>
                  </Link>
                ))}
              </nav>
              <button type="button" onClick={() => setQuery("")}>
                清除搜索
              </button>
            </div>
          ) : (
            <nav aria-label="产品文档导航">
              <Link
                className="dm-docs-home-link"
                href="/docs"
                aria-current={pathname === "/docs" ? "page" : undefined}
              >
                文档首页
              </Link>
              {docGroups.map((group) => (
                <section key={group.id}>
                  <h2>{group.title}</h2>
                  {pages
                    .filter((page) => page.group === group.id)
                    .map((page) => (
                      <Link
                        key={page.slug}
                        href={`/docs/${page.slug}`}
                        aria-current={
                          pathname === `/docs/${page.slug}` ? "page" : undefined
                        }
                      >
                        {page.title}
                      </Link>
                    ))}
                </section>
              ))}
            </nav>
          )}
        </aside>
        <main id="docs-main" className="dm-docs-main" tabIndex={-1}>
          {children}
        </main>
      </div>
    </div>
  );
}

export function DocsHome() {
  return (
    <div className="dm-docs-home">
      <p className="dm-eyebrow">DEERMATE DOCUMENTATION</p>
      <h1>产品文档</h1>
      <p className="dm-docs-lead">从交代一个目标，到检查每一步结果。</p>
      <p className="dm-docs-intro">
        了解如何使用你的私人 Agent 工作台，或深入阅读背后的系统设计与研究方法。
      </p>
      <div className="dm-docs-cards">
        {docGroups.map(({ icon: Icon, ...group }) => (
          <Link key={group.id} href={group.href}>
            <Icon size={22} />
            <small>{group.audience}</small>
            <h2>{group.title}</h2>
            <p>{group.description}</p>
            <span>
              开始阅读 <ArrowRight size={16} />
            </span>
          </Link>
        ))}
      </div>
      <section className="dm-docs-start">
        <h2>第一次使用？</h2>
        <p>
          先用一个范围清楚的小目标熟悉工作台，再按需开启记忆、关注或设备执行。
        </p>
        <Link href="/docs/guide/quickstart">
          开始第一项工作 <ArrowRight size={16} />
        </Link>
      </section>
      <aside className="dm-docs-note">
        <strong>当前为研究 Alpha</strong>
        <p>
          文档区分已有能力、可选功能与待验证方案。实例可用范围取决于版本、配置和授权；持续秘书默认关闭。
        </p>
        <p>
          本阶段提供使用指南、技术方案与变更日志。接口文档及部署指南暂不提供。
        </p>
      </aside>
    </div>
  );
}

export function DocsArticle({ slug }: { slug: string }) {
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);
  useEffect(() => {
    setCopied(false);
    setCopyError(false);
  }, [slug]);
  const page = pages.find((entry) => entry.slug === slug);
  if (!page) return null;
  const slugger = new GithubSlugger();
  const sections = [...page.body.matchAll(/^## (.+)$/gm)].map((match) => ({
    title: match[1]!,
    id: slugger.slug(match[1]!),
  }));
  const siblings = pages.filter((entry) => entry.group === page.group);
  const index = siblings.findIndex((entry) => entry.slug === slug);
  const previous = siblings[index - 1];
  const next = siblings[index + 1];
  async function copy() {
    try {
      await navigator.clipboard.writeText(`# ${page!.title}\n\n${page!.body}`);
      setCopied(true);
      setCopyError(false);
    } catch {
      setCopyError(true);
    }
  }
  return (
    <div className="dm-docs-reading">
      <article className="dm-docs-article">
        <p className="dm-docs-category">
          {docGroups.find((group) => group.id === page.group)?.title}
          {page.status !==
            docGroups.find((group) => group.id === page.group)?.title &&
            ` / ${page.status}`}
        </p>
        <h1>{page.title}</h1>
        <p className="dm-docs-description">{page.description}</p>
        <div className="dm-docs-meta">
          <span>
            更新于 <time dateTime={page.updated}>{page.updated}</time>
          </span>
          <button type="button" onClick={copy}>
            {copied ? <Check size={14} /> : <Copy size={14} />}
            {copied ? "已复制 Markdown" : "复制 Markdown"}
          </button>
        </div>
        {copyError && <p role="status">复制失败，请选择正文后手动复制。</p>}
        <div className="dm-docs-prose">
          <SafeStreamdown
            mode="static"
            plugins={{}}
            components={docComponents}
            controls={false}
            rehypePlugins={[rehypeSlug]}
          >
            {page.body}
          </SafeStreamdown>
        </div>
        <nav className="dm-docs-pagination" aria-label="相邻文档">
          {previous ? (
            <Link href={`/docs/${previous.slug}`}>
              <small>
                <ArrowLeft size={14} /> 上一篇
              </small>
              {previous.title}
            </Link>
          ) : (
            <span />
          )}
          {next && (
            <Link href={`/docs/${next.slug}`}>
              <small>
                下一篇 <ArrowRight size={14} />
              </small>
              {next.title}
            </Link>
          )}
        </nav>
        <p className="dm-docs-footer">
          以当前实例的功能与回执为准。
          <Link href="/docs/changelog">查看变更日志</Link>
        </p>
      </article>
      <nav className="dm-docs-toc" aria-label="本页目录">
        <h2>本页目录</h2>
        {sections.map((section) => (
          <a key={section.id} href={`#${section.id}`}>
            {section.title}
          </a>
        ))}
      </nav>
    </div>
  );
}
