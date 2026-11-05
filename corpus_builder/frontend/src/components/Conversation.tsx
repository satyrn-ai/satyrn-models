import { messageContent, messageRole, messageRoleLabel } from "../conversations";
import type { Message } from "../types";
import { CodeBlock } from "./CodeBlock";
import { Markdown } from "./Markdown";

function MessageCard({ message }: { message: Message }) {
  const roleClass = messageRole(message).replace(/[^a-z0-9_-]/g, "") || "message";
  const content = messageContent(message);
  const reasoning = typeof message.reasoning_content === "string" ? message.reasoning_content : "";

  return (
    <article className={`message message-${roleClass}`}>
      <header className="message-header">{messageRoleLabel(message)}</header>
      {reasoning && (
        <details className="message-thinking" open>
          <summary>Thinking</summary>
          <Markdown source={reasoning} />
        </details>
      )}
      {content === null ? (
        <div className="message-body">
          <CodeBlock code={JSON.stringify(message.content ?? message, null, 2)} language="json" />
        </div>
      ) : (
        <Markdown source={content} className="message-body" />
      )}
    </article>
  );
}

export function Conversation({ messages }: { messages: Message[] }) {
  return (
    <div className="conversation">
      {messages.map((message, index) => (
        <MessageCard key={index} message={message} />
      ))}
    </div>
  );
}
