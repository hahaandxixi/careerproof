import AccessGate from "@/components/AccessGate";
import GrowthWorkspace from "@/components/GrowthWorkspace";

export default async function GrowthPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <AccessGate roles={["student"]}><GrowthWorkspace id={id} /></AccessGate>;
}
