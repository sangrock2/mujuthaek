import { useQuery } from "@tanstack/react-query";
import { mockQuery } from "@/features/mock-query";
import { authSession } from "@/mocks/auth";

export const authKeys = {
  session: ["auth", "session"] as const,
};

export function useAuthSession() {
  return useQuery(mockQuery(authKeys.session, authSession));
}
