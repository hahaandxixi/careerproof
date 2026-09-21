import AccessGate from "@/components/AccessGate";
import CareerRecommendations from "@/components/CareerRecommendations";

export default function RecommendationsPage() {
  return <AccessGate roles={["student"]}><CareerRecommendations /></AccessGate>;
}
