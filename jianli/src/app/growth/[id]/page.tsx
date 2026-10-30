import AccessGate from "@/components/AccessGate";
import GrowthHistory from "@/components/GrowthHistory";

export default async function GrowthPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <AccessGate roles={["student"]}><GrowthHistory id={id} /></AccessGate>;
}
