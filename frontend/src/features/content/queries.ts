import { USE_MOCKS } from "@/shared/lib/api/config";
import { useQuery } from "@tanstack/react-query";
import { mockQuery } from "@/features/mock-query";
import { announcements, faq, statesPreview, type FaqData } from "@/features/content/mocks/content";
import { privacy, terms } from "@/features/content/mocks/content-legal";
import { LEGAL_CONTACT } from "@/features/content/legal/documents";

export const contentKeys = {
  announcements: ["content", "announcements"] as const,
  faq: ["content", "faq"] as const,
  terms: ["content", "terms"] as const,
  privacy: ["content", "privacy"] as const,
  statesPreview: ["content", "states-preview"] as const,
};

export function useAnnouncements() {
  return useQuery(mockQuery(contentKeys.announcements, USE_MOCKS ? announcements : []));
}

const liveFaq: FaqData = {
  initiallyOpen: ["f1"],
  contact: { email: LEGAL_CONTACT, hours: "이메일 접수 · 확인 후 회신" },
  web: [
    {
      id: "f1",
      category: "공고·혜택",
      question: "현재 공고가 보이지 않아요",
      answer:
        "기관별 공고 연동을 준비하고 있어요. 등록된 공고가 없으면 목록에 표시되지 않아요. 최신 공고와 접수 일정은 기관 원문에서 확인해 주세요.",
    },
    {
      id: "f2",
      category: "판정·자격",
      question: "판정 결과만 보고 신청해도 되나요?",
      answer:
        "판정은 참고용이에요. 최종 자격은 각 기관이 심사하므로 신청 전에 공고 원문을 확인해 주세요.",
    },
    {
      id: "f3",
      category: "계정·개인정보",
      question: "로그인은 바로 사용할 수 있나요?",
      answer:
        "카카오·Google 계정으로 로그인할 수 있어요. 로그인하면 관심 공고와 신청 준비함을 계정에 저장할 수 있고, 공개 공고 조회와 조건 확인은 로그인 없이도 이용할 수 있어요.",
    },
    {
      id: "f4",
      category: "알림",
      question: "알림을 받을 수 있나요?",
      answer: "외부 알림 발송은 준비 중이에요. 신청 일정은 기관 원문에서 직접 확인해 주세요.",
    },
  ],
  mobile: [],
};
liveFaq.mobile = liveFaq.web;

export function useFaq() {
  return useQuery(mockQuery(contentKeys.faq, USE_MOCKS ? faq : liveFaq));
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
