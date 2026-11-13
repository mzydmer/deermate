export const dynamic = "force-dynamic";
import { notFound } from "next/navigation";

import { LegacyContracts } from "@/components/deermate/patterns/legacy-contracts";
export default function Page() {
  if (process.env.DEERMATE_DESIGN_GALLERY !== "1") notFound();
  return <LegacyContracts />;
}
