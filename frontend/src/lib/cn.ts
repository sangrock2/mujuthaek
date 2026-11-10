import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// globals.css @theme의 이름을 알려줘야 덮어쓰기가 맞게 합쳐져요
const twMerge = extendTailwindMerge({
  extend: {
    theme: {
      radius: ["tag", "badge", "sm", "control", "tile", "card", "card-lg", "pill"],
      shadow: ["seg", "float"],
      tracking: ["body", "title", "h1", "logo"],
    },
  },
});

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
