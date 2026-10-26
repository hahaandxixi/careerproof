const UUID_PREFIX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\//;
const UUID_PREFIX_ANYWHERE = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\//g;

/** Remove the internal material-version UUID from a displayed file path. */
export function displayFilePath(filePath: string): string {
  return filePath.replace(UUID_PREFIX, "");
}

/** Remove UUID path prefixes embedded in saved explanations and gap text. */
export function displayFilePathText(text: string): string {
  return text.replace(UUID_PREFIX_ANYWHERE, "");
}
