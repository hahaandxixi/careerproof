// 合成静态练习，未运行；不证明本人贡献。
import { useState } from "react";

type Task = { id: number; title: string };
export function TaskList() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  async function load() {
    setLoading(true); setError("");
    try {
      const response = await fetch("/api/tasks");
      if (!response.ok) throw new Error("加载失败");
      setTasks(await response.json());
    } catch { setError("加载失败，请重试"); }
    finally { setLoading(false); }
  }
  return <section>
    <button disabled={loading} onClick={load}>加载任务</button>
    {loading && <p role="status">加载中</p>}
    {error && <p role="alert">{error}</p>}
    {!loading && !error && !tasks.length && <p>暂无任务</p>}
    <ul className="tasks">{tasks.map(task => <li key={task.id}>{task.title}</li>)}</ul>
  </section>;
}
