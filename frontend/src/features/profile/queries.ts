import { useQuery } from "@tanstack/react-query";
import { mockQuery } from "@/features/mock-query";
import { profileFormData } from "@/features/profile/mocks/profile";

export const profileKeys = {
  form: ["profile", "form"] as const,
};

export function useProfileFormData() {
  return useQuery(mockQuery(profileKeys.form, profileFormData));
}
