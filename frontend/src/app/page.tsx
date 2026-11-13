import { Responsive } from "@/shared/layout/Responsive";
import { MMain } from "@/features/main/screens/MMain";
import { WebMain } from "@/features/main/screens/WebMain";

export default function MainPage() {
  return <Responsive web={<WebMain />} mobile={<MMain />} />;
}
