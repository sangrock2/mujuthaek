import { useQuery } from "@tanstack/react-query";
import { mockQuery } from "@/features/mock-query";
import { homesSummary } from "@/mocks/homes";

export const homesKeys = {
  summary: ["homes", "summary"] as const,
};

export function useHomes() {
  return useQuery(mockQuery(homesKeys.summary, homesSummary));
}
