import { useState } from "react";

type Activity = { id: number; title: string; remaining: number };
const activities: Activity[] = [
  { id: 1, title: "Python学习小组", remaining: 8 },
  { id: 2, title: "开源项目分享", remaining: 0 },
];

export default function ActivityList() {
  const [query, setQuery] = useState("");
  const visible = activities.filter(item => item.title.includes(query.trim()));
  return <section aria-labelledby="activity-title">
    <h1 id="activity-title">校园活动</h1>
    <label htmlFor="activity-search">搜索活动</label>
    <input id="activity-search" value={query}
      onChange={event => setQuery(event.target.value)} />
    <p aria-live="polite">共{visible.length}个活动</p>
    {!visible.length && <p>没有匹配的活动，请调整关键词。</p>}
    <ul className="activity-list">{visible.map(item => <li key={item.id}>
      <h2>{item.title}</h2><p>剩余名额：{item.remaining}</p>
    </li>)}</ul>
  </section>;
}
