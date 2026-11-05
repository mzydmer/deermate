import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { DocsArticle } from "@/components/deermate/product-docs";
import pages from "@/components/deermate/product-docs.generated.json";

export const dynamicParams = false;

export function generateStaticParams() {
  return pages.map((page) => ({ slug: page.slug.split("/") }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string[] }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const page = pages.find((entry) => entry.slug === slug.join("/"));
  return { title: page?.title, description: page?.description };
}

export default async function DocPage({
  params,
}: {
  params: Promise<{ slug: string[] }>;
}) {
  const { slug } = await params;
  const key = slug.join("/");
  if (!pages.some((page) => page.slug === key)) notFound();
  return <DocsArticle key={key} slug={key} />;
}
