import AccessGate from "@/components/AccessGate";
import TaskView from "@/components/TaskView";
export default async function TaskPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <AccessGate roles={["student", "admin"]}><TaskView id={id} /></AccessGate>;
}
