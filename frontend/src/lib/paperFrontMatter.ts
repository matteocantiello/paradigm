/**
 * Split a paper body's front matter (leading `# Title` + `Abstract` section)
 * from the rest. The paper viewer renders its own styled title header and
 * abstract box, so leaving them in the body showed both TWICE — and the DB
 * `abstract` column is truncated at 1000 chars, so the body's full abstract
 * is preferred where present.
 */
export function splitPaperFrontMatter(body: string): {
  title: string | null;
  abstract: string | null;
  rest: string;
} {
  const lines = (body ?? "").split("\n");
  let i = 0;
  while (i < lines.length && lines[i].trim() === "") i++;

  let title: string | null = null;
  if (i < lines.length && /^#\s+\S/.test(lines[i])) {
    title = lines[i].replace(/^#\s+/, "").trim();
    i++;
  }
  while (i < lines.length && lines[i].trim() === "") i++;

  let abstract: string | null = null;
  if (i < lines.length && /^#{1,3}\s*abstract\s*$/i.test(lines[i].trim())) {
    i++;
    const collected: string[] = [];
    while (i < lines.length && !/^#{1,6}\s+\S/.test(lines[i])) {
      collected.push(lines[i]);
      i++;
    }
    abstract = collected.join("\n").trim() || null;
  }
  return { title, abstract, rest: lines.slice(i).join("\n").trimStart() };
}
