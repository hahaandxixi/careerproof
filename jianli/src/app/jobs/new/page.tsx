import AccessGate from "@/components/AccessGate";
import JobForm from "@/components/JobForm";
export default function NewJobPage() {
  return <AccessGate roles={["enterprise", "admin"]}><JobForm /></AccessGate>;
}
