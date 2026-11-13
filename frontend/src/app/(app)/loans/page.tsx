import type { Metadata } from "next";
import { Responsive } from "@/shared/layout/Responsive";
import { MLoans } from "@/features/loans/screens/MLoans";
import { WebLoans } from "@/features/loans/screens/WebLoans";

export const metadata: Metadata = { title: "대출 자격 확인 | 무주택자들" };

export default function LoansPage() {
  return <Responsive web={<WebLoans />} mobile={<MLoans />} />;
}
