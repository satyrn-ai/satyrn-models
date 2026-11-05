import { Fragment } from "react";
import { humanizeKey } from "../items";

export function Metadata({ metadata }: { metadata: Record<string, unknown> }) {
  return (
    <dl className="metadata">
      {Object.entries(metadata).map(([key, value]) => (
        <Fragment key={key}>
          <dt>{humanizeKey(key)}</dt>
          <dd>{typeof value === "string" ? value : JSON.stringify(value)}</dd>
        </Fragment>
      ))}
    </dl>
  );
}
