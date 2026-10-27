import JobList from "@/components/JobList";
import { Suspense } from "react";
export default function JobsPage() {
  return <Suspense fallback={<p role="status" className="panel">正在读取岗位筛选…</p>}><JobList/></Suspense>;
}
