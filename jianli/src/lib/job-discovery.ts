import taxonomy from "./technical-careers.json";
import { CATEGORY_LABELS, EMPLOYMENT_LABELS } from "./api/domain";

// Generated JSON comes from backend/app/data/technical-careers.json, never from an API scrape.
export const CAREER_DIRECTIONS = taxonomy.directions;
export const CAREER_LANGUAGES = taxonomy.languages;
export interface DiscoveryQuery {
  direction: string; specialty: string; language: string; q: string;
  city: string; employmentType: string; category: string; page: number;
}
export const EMPTY_DISCOVERY: DiscoveryQuery = {
  direction: "", specialty: "", language: "", q: "", city: "", employmentType: "", category: "", page: 1,
};
export function readDiscoveryQuery(params: { get(name: string): string | null }): DiscoveryQuery {
  const rawDirection = params.get("direction");
  const direction = CAREER_DIRECTIONS.find(item => item.id === rawDirection);
  const specialty = direction?.specialties.find(item => item.id === params.get("specialty"));
  const language = CAREER_LANGUAGES.find(item => item.id === params.get("language"));
  const employment = params.get("employmentType") || "";
  const category = params.get("category") || "";
  const page = params.get("page") || "";
  return {
    direction: direction?.id ?? "", specialty: specialty?.id ?? "", language: language?.id ?? "",
    q: (params.get("q") || "").trim().slice(0, 200), city: (params.get("city") || "").trim().slice(0, 100),
    employmentType: Object.hasOwn(EMPLOYMENT_LABELS, employment) ? employment : "",
    category: Object.hasOwn(CATEGORY_LABELS, category) ? category : "",
    page: /^\d{1,7}$/.test(page) ? Math.max(1, Math.min(1_000_000, Number(page))) : 1,
  };
}
export function discoveryHref(query: DiscoveryQuery): string {
  const params = new URLSearchParams();
  for (const key of ["direction", "specialty", "language", "city", "employmentType", "category", "q"] as const) {
    if (query[key]) params.set(key, query[key]);
  }
  if (query.page > 1) params.set("page", String(query.page));
  return `/jobs${params.size ? `?${params}` : ""}`;
}
export function directionLabel(id?: string | null): string | null {
  return CAREER_DIRECTIONS.find(item => item.id === id)?.label ?? null;
}
