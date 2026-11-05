import { collectMessages } from "../conversations";
import { humanizeKey, isCodeKey, itemSubtitle, itemTitle, KNOWN_KEYS } from "../items";
import type { DatasetItem } from "../types";
import { CodeBlock } from "./CodeBlock";
import { Conversation } from "./Conversation";
import { Markdown } from "./Markdown";
import { Metadata } from "./Metadata";
import { Section } from "./Section";
import { TestCaseCard } from "./TestCaseCard";

function GenericValue({ name, value }: { name: string; value: unknown }) {
  if (typeof value === "string") {
    return isCodeKey(name) ? <CodeBlock code={value} /> : <Markdown source={value} />;
  }
  return <CodeBlock code={JSON.stringify(value, null, 2)} language="json" />;
}

export function ItemView({ item }: { item: DatasetItem }) {
  const index = item._viewer?.index ?? 0;
  const messages = collectMessages(item);
  const extraFields = Object.entries(item).filter(
    ([key, value]) => !KNOWN_KEYS.has(key) && value !== null && value !== undefined && value !== "",
  );

  return (
    <article className="item">
      <header className="item-header">
        <h2>{itemTitle(item, index)}</h2>
        <p className="item-subtitle">{itemSubtitle(item)}</p>
      </header>

      {item.metadata && Object.keys(item.metadata).length > 0 && (
        <Section title="Metadata">
          <Metadata metadata={item.metadata} />
        </Section>
      )}

      {messages.length > 0 ? (
        <Section title="Conversation">
          <Conversation messages={messages} />
        </Section>
      ) : (
        typeof item.prompt === "string" &&
        item.prompt && (
          <Section title="Prompt">
            <Markdown source={item.prompt} />
          </Section>
        )
      )}

      {typeof item.solution === "string" && item.solution && (
        <Section title="Reference solution">
          <CodeBlock code={item.solution} />
        </Section>
      )}

      {Array.isArray(item.test_cases) && item.test_cases.length > 0 && (
        <Section title={`Test cases (${item.test_cases.length})`}>
          <div className="test-cases">
            {item.test_cases.map((testCase, testIndex) => (
              <TestCaseCard key={testIndex} testCase={testCase} index={testIndex} />
            ))}
          </div>
        </Section>
      )}

      {extraFields.map(([key, value]) => (
        <Section key={key} title={humanizeKey(key)}>
          <GenericValue name={key} value={value} />
        </Section>
      ))}
    </article>
  );
}
