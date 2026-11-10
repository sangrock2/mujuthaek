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
    title: "마감 전에 알림",
    desc: "관심 등록한 공고와 혜택은 접수 시작과 마감 전에 알려드려요",
  },
];

export const trust: { icon: LucideIcon; title: string; desc: string }[] = [
  {
    icon: Lock,
    title: "소득·자산은 저장하지 않아요",
    desc: "판정할 때만 쓰고 어디에도 저장하지 않아요. 나머지 조건은 이 기기에만 30일 동안 둬요",
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
    a: "LH와 청약홈은 전국 공고를, 지방 공사는 서울·경기·인천·부산·대구·대전·울산·경북·경남 공고를 모아요.",
  },
  {
    q: "새 공고는 얼마나 빨리 올라오나요?",
    a: "평일 근무 시간에는 기관 게시판을 매시간 확인해요. 내 조건에 맞는 새 공고가 나오면 알림으로 알려드려요.",
  },
];
