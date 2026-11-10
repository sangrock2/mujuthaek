import { useQuery } from "@tanstack/react-query";
import { mockQuery } from "@/features/mock-query";
import { mainLanding } from "@/mocks/main";

export const mainKeys = {
  landing: ["main", "landing"] as const,
};

export function useMainLanding() {
  return useQuery(mockQuery(mainKeys.landing, mainLanding));
}
