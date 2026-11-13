import { messageContent, messageRole, messageRoleLabel, messageToolCalls } from "../conversations";
import type { Message } from "../types";
import { CodeBlock } from "./CodeBlock";
import { Markdown } from "./Markdown";

function MessageBody({ role, content }: { role: string; content: string }) {
  if (role === "tool") {
    return (
      <div className="message-body">
        <CodeBlock code={content} language="text" />
      </div>
    );
  }
  return <Markdown source={content} className="message-body" />;
}

function MessageCard({ message }: { message: Message }) {
  const roleClass = messageRole(message).replace(/[^a-z0-9_-]/g, "") || "message";
  const content = messageContent(message);
  const toolCalls = messageToolCalls(message);
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
      {content !== null && <MessageBody role={roleClass} content={content} />}
      {content === null && toolCalls.length === 0 && (
        <div className="message-body">
          <CodeBlock code={JSON.stringify(message.content ?? message, null, 2)} language="json" />
        </div>
      )}
      {toolCalls.map((call, index) => (
        <div key={index} className="message-body">
          <strong>{call.name}</strong>
          {Object.entries(call.arguments).map(([name, value]) => (
            <CodeBlock
              key={name}
              code={typeof value === "string" ? value : JSON.stringify(value, null, 2)}
              language={name === "command" ? "bash" : "python"}
            />
          ))}
        </div>
      ))}
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
