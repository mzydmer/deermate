import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

import { typographyUtilities } from "./design-utilities.generated";
const merge = extendTailwindMerge({
  extend: {
    classGroups: { "font-size": [{ text: [...typographyUtilities] }] },
  },
});
export function cn(...inputs: ClassValue[]) {
  return merge(clsx(inputs));
}
