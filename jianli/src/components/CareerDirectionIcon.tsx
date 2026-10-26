const paths: Record<string, React.ReactNode> = {
  backend: <><rect x="4" y="3" width="16" height="7" rx="2"/><rect x="4" y="14" width="16" height="7" rx="2"/><path d="M8 6.5h.01M8 17.5h.01M12 6.5h5M12 17.5h5"/></>,
  frontend: <><rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8M12 17v4M8 9l-2 2 2 2m8-4 2 2-2 2"/></>,
  testing: <><path d="M12 3 4 6v5c0 5 8 10 8 10s8-5 8-10V6l-8-3Z"/><path d="m8 12 3 3 5-6"/></>,
  data: <><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v7c0 4 16 4 16 0V5M4 12v7c0 4 16 4 16 0v-7"/></>,
  ai: <><path d="M9 4a3 3 0 0 0-5 3v1a3 3 0 0 0-1 5 4 4 0 0 0 3 6 3 3 0 0 0 6 0V5a3 3 0 0 0-3-1Zm6 0a3 3 0 0 1 5 3v1a3 3 0 0 1 1 5 4 4 0 0 1-3 6 3 3 0 0 1-6 0"/><path d="M7 9h2m6 6h2M6 15h3m6-6h3"/></>,
  cloud: <><path d="M6 19a5 5 0 0 1-1-10 7 7 0 0 1 13-2 6 6 0 0 1 0 12Z"/><path d="m9 13 3-3 3 3m-3-3v8"/></>,
  product: <><rect x="9" y="3" width="6" height="6" rx="1"/><rect x="3" y="15" width="6" height="6" rx="1"/><rect x="15" y="15" width="6" height="6" rx="1"/><path d="M12 9v3m-6 3v-3h12v3"/></>,
};
export default function CareerDirectionIcon({ direction, className = "h-5 w-5" }: { direction: string; className?: string }) {
  return <svg aria-hidden="true" className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">{paths[direction] ?? paths.backend}</svg>;
}
