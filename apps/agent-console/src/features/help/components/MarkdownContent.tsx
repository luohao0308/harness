import { JargonText } from "../../../components/ui/term";

type Block =
  | { type: "heading"; level: number; text: string }
  | { type: "paragraph"; text: string }
  | { type: "list"; items: string[] }
  | { type: "code"; language: string; code: string };

export function MarkdownContent({ source }: { source: string }) {
  const blocks = parseMarkdown(source);
  return (
    <article className="help-content space-y-4 text-sm leading-6 text-slate-700">
      {blocks.map((block, index) => {
        if (block.type === "heading") {
          const Tag = block.level === 1 ? "h1" : block.level === 2 ? "h2" : "h3";
          return (
            <Tag key={index} className={block.level === 1 ? "text-xl font-semibold text-slate-950" : "text-base font-semibold text-slate-900"}>
              <JargonText>{block.text}</JargonText>
            </Tag>
          );
        }
        if (block.type === "list") {
          return (
            <ul key={index} className="list-disc space-y-1 pl-5">
              {block.items.map((item) => (
                <li key={item}>
                  <JargonText>{item}</JargonText>
                </li>
              ))}
            </ul>
          );
        }
        if (block.type === "code") {
          return (
            <pre key={index} className="overflow-x-auto rounded-md bg-slate-950 p-3 text-xs leading-5 text-slate-50">
              <code>{block.code}</code>
            </pre>
          );
        }
        return (
          <p key={index}>
            <JargonText>{block.text}</JargonText>
          </p>
        );
      })}
    </article>
  );
}

function parseMarkdown(source: string): Block[] {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  let list: string[] = [];
  let code: string[] = [];
  let codeLanguage = "";
  let inCodeBlock = false;

  const flushParagraph = () => {
    if (paragraph.length) {
      blocks.push({ type: "paragraph", text: paragraph.join(" ") });
      paragraph = [];
    }
  };
  const flushList = () => {
    if (list.length) {
      blocks.push({ type: "list", items: list });
      list = [];
    }
  };

  for (const line of lines) {
    if (inCodeBlock || line.startsWith("```")) {
      if (line.startsWith("```")) {
        if (inCodeBlock) {
          blocks.push({ type: "code", language: codeLanguage, code: code.join("\n") });
          code = [];
          codeLanguage = "";
          inCodeBlock = false;
        } else {
          flushParagraph();
          flushList();
          code = [];
          codeLanguage = line.slice(3).trim();
          inCodeBlock = true;
        }
        continue;
      }
      code.push(line);
      continue;
    }
    const trimmed = line.trim();
    if (!trimmed) {
      flushParagraph();
      flushList();
      continue;
    }
    const heading = /^(#{1,3})\s+(.+)$/.exec(trimmed);
    if (heading) {
      flushParagraph();
      flushList();
      blocks.push({ type: "heading", level: heading[1].length, text: heading[2] });
      continue;
    }
    if (trimmed.startsWith("- ")) {
      flushParagraph();
      list.push(trimmed.slice(2));
      continue;
    }
    paragraph.push(trimmed);
  }
  if (inCodeBlock) {
    blocks.push({ type: "code", language: codeLanguage, code: code.join("\n") });
  }
  flushParagraph();
  flushList();
  return blocks;
}
