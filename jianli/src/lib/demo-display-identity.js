// Verified existing fixture identities only. Never infer example status from names.
const identities = [
  {
    "userId": "3e1e80a0-c7e0-4203-9aa9-f770b7ba3fe3",
    "displayName": "陈同学",
    "applicationIds": [
      "efd038f0-cf48-4791-a8e3-288dcae5991e"
    ]
  },
  {
    "userId": "b5ec33cb-c669-4ae5-8a86-c1a591f5d2de",
    "displayName": "林同学",
    "applicationIds": [
      "3724815b-78c4-4229-b98a-80da1ab00209",
      "3f3a6e0f-d272-4748-8825-b485f2737089"
    ]
  },
  {
    "userId": "a12657c4-48d1-436c-96c9-857243294838",
    "displayName": "周同学",
    "applicationIds": [
      "1ae5fdce-d44c-4a58-9c3c-ea52799c0d38"
    ]
  },
  {
    "userId": "b0bfd306-2277-4b1c-91d7-07920ab52e0e",
    "displayName": "赵同学",
    "applicationIds": [
      "642fbe12-8cc8-4948-84c5-fcee21a228a7"
    ]
  }
];

export function displayIdentity(originalName, identityId) {
  const known = identityId && identities.find(item => item.userId === identityId || item.applicationIds.includes(identityId));
  return { name: known ? known.displayName : originalName, originalName, isExample: Boolean(known) };
}

export function identityLabel(originalName, identityId) {
  const value = displayIdentity(originalName, identityId);
  return value.isExample ? `${value.name} · 示例` : value.name;
}
