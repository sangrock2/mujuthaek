import type { Metadata } from "next";
import { Responsive } from "@/components/layout/Responsive";
import { MLoans } from "@/screens/loans/MLoans";
import { WebLoans } from "@/screens/loans/WebLoans";

export const metadata: Metadata = { title: "대출 자격 확인 | 무주택자들" };

export default function LoansPage() {
  return <Responsive web={<WebLoans />} mobile={<MLoans />} />;
}
