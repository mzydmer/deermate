export const dynamic = "force-dynamic";
import { DesignGallery } from "@/components/deermate/ui/gallery";
import { notFound } from "next/navigation";
export default function DesignPage() {
  if (process.env.DEERMATE_DESIGN_GALLERY !== "1") notFound();
  return <DesignGallery />;
}
