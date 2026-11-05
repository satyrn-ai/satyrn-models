import type { TestCase } from "../types";
import { CodeBlock } from "./CodeBlock";

interface TestCaseCardProps {
  testCase: TestCase;
  index: number;
}

export function TestCaseCard({ testCase, index }: TestCaseCardProps) {
  const fields: [string, string | undefined][] = [
    ["Input", testCase.input],
    ["Expected output", testCase.expected_output],
  ];
  const presentFields = fields.filter((field): field is [string, string] => field[1] !== undefined);

  return (
    <article className="test-case">
      <h4>
        <span className="badge">{index + 1}</span>
        <span>{testCase.name ?? `Test ${index + 1}`}</span>
      </h4>
      {presentFields.length > 0 && (
        <div className="test-grid">
          {presentFields.map(([label, value]) => (
            <div key={label}>
              <span className="field-label">{label}</span>
              <CodeBlock code={value} />
            </div>
          ))}
        </div>
      )}
      {testCase.test_code && (
        <>
          <span className="field-label">Test code</span>
          <CodeBlock code={testCase.test_code} />
        </>
      )}
    </article>
  );
}
