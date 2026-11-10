import { useQuery } from "@tanstack/react-query";
import { mockQuery } from "@/features/mock-query";
import { scoreProfile } from "@/mocks/score";

export const scoreKeys = {
  profile: ["score", "profile"] as const,
};

export function useScoreProfile() {
  return useQuery(mockQuery(scoreKeys.profile, scoreProfile));
}
