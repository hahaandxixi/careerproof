import AccessGate from "@/components/AccessGate";
import ReportList from "@/components/ReportList";
export default function ReportsPage() { return <AccessGate roles={["student", "admin"]}><ReportList /></AccessGate>; }
