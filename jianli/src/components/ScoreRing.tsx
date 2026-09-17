/** 环形得分展示（SVG） */
export default function ScoreRing({
  score,
  size = 88,
}: {
  score: number;
  size?: number;
}) {
  const stroke = 8;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, score));
  const color = pct >= 80 ? "#10b981" : pct >= 60 ? "#6366f1" : "#f43f5e";

  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="#e2e8f0"
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeDasharray={c}
          strokeDashoffset={c - (c * pct) / 100}
          strokeLinecap="round"
        />
      </svg>
      <div className="absolute text-center">
        <div className="text-xl font-bold" style={{ color }}>
          {score}
        </div>
        <div className="text-[10px] text-slate-400">匹配度</div>
      </div>
    </div>
  );
}
