// Verified existing fixture identities only. Never infer example status from names.
const identities = [
  {
    "userId": "3e1e80a0-c7e0-4203-9aa9-f770b7ba3fe3",
    "displayName": "陈同学"
  },
  {
    "userId": "b5ec33cb-c669-4ae5-8a86-c1a591f5d2de",
    "displayName": "林同学"
  },
  {
    "userId": "a12657c4-48d1-436c-96c9-857243294838",
    "displayName": "周同学"
  },
  {
    "userId": "b0bfd306-2277-4b1c-91d7-07920ab52e0e",
    "displayName": "赵同学"
  }
];

export function displayIdentity(originalName, identityId) {
  const known = identityId && identities.find(item => item.userId === identityId);
  return { name: known ? known.displayName : originalName, originalName, isExample: Boolean(known) };
}

export function identityLabel(originalName, identityId) {
  const value = displayIdentity(originalName, identityId);
  return value.isExample ? `${value.name} · 示例` : value.name;
}
