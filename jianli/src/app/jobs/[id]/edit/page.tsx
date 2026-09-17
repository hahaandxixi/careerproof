import AccessGate from "@/components/AccessGate";
import JobForm from "@/components/JobForm";
export default async function EditJobPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <AccessGate roles={["enterprise", "admin"]}><JobForm jobId={id} /></AccessGate>;
}
