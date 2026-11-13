export const dynamic = "force-dynamic";
import { notFound } from "next/navigation";

import { DesignGallery } from "@/components/deermate/ui/gallery";
export default function DesignPage() {
  if (process.env.DEERMATE_DESIGN_GALLERY !== "1") notFound();
  return <DesignGallery />;
}
