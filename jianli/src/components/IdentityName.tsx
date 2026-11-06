import { displayIdentity } from "@/lib/demo-display-identity.js";

export default function IdentityName({ name, identityId }: { name: string; identityId?: string }) {
  return displayIdentity(name, identityId).name;
}
