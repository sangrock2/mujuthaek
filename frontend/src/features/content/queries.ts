import { useQuery } from "@tanstack/react-query";
import { mockQuery } from "@/features/mock-query";
import { announcements, faq, statesPreview } from "@/mocks/content";
import { privacy, terms } from "@/mocks/content-legal";

export const contentKeys = {
  announcements: ["content", "announcements"] as const,
  faq: ["content", "faq"] as const,
  terms: ["content", "terms"] as const,
  privacy: ["content", "privacy"] as const,
  statesPreview: ["content", "states-preview"] as const,
};

export function useAnnouncements() {
  return useQuery(mockQuery(contentKeys.announcements, announcements));
}

export function useFaq() {
  return useQuery(mockQuery(contentKeys.faq, faq));
}

export function useTerms() {
  return useQuery(mockQuery(contentKeys.terms, terms));
}

export function usePrivacy() {
  return useQuery(mockQuery(contentKeys.privacy, privacy));
}

export function useStatesPreview() {
  return useQuery(mockQuery(contentKeys.statesPreview, statesPreview));
}
