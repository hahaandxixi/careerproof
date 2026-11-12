import { Suspense } from "react";
import ApplicationList from "@/components/ApplicationList";

export default function Page() {
  return <Suspense fallback={<p role="status">正在打开求职工作台…</p>}><ApplicationList /></Suspense>;
}
