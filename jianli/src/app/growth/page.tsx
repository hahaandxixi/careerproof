import AccessGate from "@/components/AccessGate";
import GrowthWorkspace from "@/components/GrowthWorkspace";

export default function GrowthListPage() {
  return <AccessGate roles={["student"]}><GrowthWorkspace /></AccessGate>;
}
