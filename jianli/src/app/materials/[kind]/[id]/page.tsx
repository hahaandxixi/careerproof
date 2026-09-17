import { notFound } from "next/navigation";
import AccessGate from "@/components/AccessGate";
import MaterialPreview from "@/components/MaterialPreview";
export default async function MaterialPage({ params }: { params: Promise<{ id: string; kind: string }> }) {
  const { id, kind } = await params;
  if (kind !== "resume" && kind !== "project") notFound();
  return <AccessGate roles={["student"]}><MaterialPreview id={id} kind={kind} /></AccessGate>;
}
