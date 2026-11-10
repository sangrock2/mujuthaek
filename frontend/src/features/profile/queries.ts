import { useQuery } from "@tanstack/react-query";
import { mockQuery } from "@/features/mock-query";
import { profileFormData } from "@/mocks/profile";

export const profileKeys = {
  form: ["profile", "form"] as const,
};

export function useProfileFormData() {
  return useQuery(mockQuery(profileKeys.form, profileFormData));
}
