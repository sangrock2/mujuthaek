import { Responsive } from "@/components/layout/Responsive";
import { MMain } from "@/screens/main/MMain";
import { WebMain } from "@/screens/main/WebMain";

export default function MainPage() {
  return <Responsive web={<WebMain />} mobile={<MMain />} />;
}
