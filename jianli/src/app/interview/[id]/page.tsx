import AccessGate from "@/components/AccessGate";
import InterviewPractice from "@/components/InterviewPractice";

export default async function InterviewPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <AccessGate roles={["student", "admin"]}><InterviewPractice id={id} /></AccessGate>;
}
