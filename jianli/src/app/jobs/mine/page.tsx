import AccessGate from "@/components/AccessGate";
import JobList from "@/components/JobList";
export default function MyJobsPage() { return <AccessGate roles={["enterprise", "admin"]}><JobList mine /></AccessGate>; }
