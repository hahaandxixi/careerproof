import AccessGate from "@/components/AccessGate";
import ReportDetail from "@/components/ReportDetail";
export default async function ReportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <AccessGate roles={["student", "admin"]}><ReportDetail id={id} /></AccessGate>;
}
