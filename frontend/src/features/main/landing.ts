// 소개(메인) 화면의 문구 묶음: 웹·모바일이 같은 내용을 보여요 (예전엔 화면마다 따로 적어 모바일에서 빠지거나 달랐어요)
import {
  BellRing,
  ListChecks,
  Lock,
  MessageSquareWarning,
  Scale,
  User,
  type LucideIcon,
} from "lucide-react";

export const howSteps: { icon: LucideIcon; title: string; desc: string }[] = [
  {
    icon: User,
    title: "조건 입력",
    desc: "나이, 거주지, 소득, 무주택 기간을 알려주세요. 모르는 칸은 비워도 돼요",
  },
  {
    icon: ListChecks,
    title: "판정 결과 확인",
    desc: "지원 가능한 공고와 받을 수 있는 혜택을 판정 근거와 함께 보여드려요",
  },
  {
    icon: BellRing,
    title: "신청 준비",
    desc: "관심 공고를 저장하고 신청 준비함에서 마감과 할 일을 확인해요",
  },
];

export const trust: { icon: LucideIcon; title: string; desc: string }[] = [
  {
    icon: Lock,
    title: "금융 정보는 판정할 때만 사용해요",
    desc: "주거 조건의 소득·자산은 이 탭에 임시 보관하고 서버에는 구간으로 보내요. 대출 확인은 정확한 금액을 서버로 보내 판정하며, 입력값을 서버 DB에 보관하지 않아요",
  },
  {
    icon: Scale,
    title: "판정은 참고용이에요",
    desc: "최종 자격은 공고 원문과 기관에서 정해져요. 그래서 원문 링크를 꼭 함께 보여드려요",
  },
  {
    icon: MessageSquareWarning,
    title: "틀린 정보는 바로 제보",
    desc: "빠진 정책이나 판정 오류를 알려주시면 확인해서 반영해요",
  },
];

export const faqs = [
  {
    q: "회원가입을 해야 하나요?",
    a: "아니요. 로그인 없이 조건을 입력하면 바로 결과를 볼 수 있어요. 관심 공고와 알림을 저장하고 싶을 때만 로그인하면 돼요.",
  },
  {
    q: "판정 결과는 믿어도 되나요?",
    a: "공고 원문을 바탕으로 판정하고 근거 문장을 함께 보여드려요. 다만 최종 자격은 기관 심사로 정해져서, 신청 전에 원문을 꼭 확인해 주세요.",
  },
  {
    q: "어느 지역 공고까지 나오나요?",
    a: "기관·지역마다 제공 범위가 달라요. 공고 목록에서 지역을 골라 확인할 수 있어요. 검색 결과가 없더라도 해당 지역의 모든 공고가 없다는 뜻은 아니에요.",
  },
  {
    q: "새 공고는 얼마나 빨리 올라오나요?",
    a: "기관별로 수집·반영 시점이 달라 즉시 반영을 보장하지 않아요. 공고 상세의 정정 이력과 원문을 함께 확인해 주세요. 조회한 날짜와 기관이 공고를 갱신한 날짜는 다를 수 있어요.",
  },
];
