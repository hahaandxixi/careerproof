import AccessGate from "@/components/AccessGate";
import GrowthHistory from "@/components/GrowthHistory";

export default function GrowthListPage() {
  return <AccessGate roles={["student"]}><GrowthHistory /></AccessGate>;
}
