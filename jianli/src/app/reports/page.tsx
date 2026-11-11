import AccessGate from "@/components/AccessGate";
import ReportList from "@/components/ReportList";
import { Suspense } from "react";
export default function ReportsPage() { return <AccessGate roles={["student", "admin"]}><Suspense><ReportList /></Suspense></AccessGate>; }
