/** Helpers for recognizing and normalizing chat-style dataset rows. */

import type { DatasetItem, Message } from "./types";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Return true when value looks like a chat message object. */
export function isMessage(value: unknown): value is Message {
  return isRecord(value) && (typeof value.role === "string" || "content" in value);
}

function toMessages(value: unknown, fallbackRole: string): Message[] {
  if (typeof value === "string") {
    return value.trim() ? [{ role: fallbackRole, content: value }] : [];
  }
  if (Array.isArray(value) && value.length > 0 && value.every(isMessage)) {
    return value as Message[];
  }
  return [];
}

/**
 * Return the chat messages for a row, combining `prompt`/`completion` pairs.
 *
 * SFT rows store user turns in `prompt` and assistant turns in `completion`; a
 * plain string prompt is treated as a single user message. Rows without
 * recognizable messages return an empty list so the caller can fall back to the
 * generic field renderer.
 */
export function collectMessages(item: DatasetItem): Message[] {
  if (Array.isArray(item.messages) && item.messages.length > 0 && item.messages.every(isMessage)) {
    return item.messages;
  }
  const completion = toMessages(item.completion, "assistant");
  if (typeof item.trace === "string" && item.trace && completion.length > 0) {
    completion[0] = { ...completion[0], reasoning_content: item.trace };
  }
  return [...toMessages(item.prompt, "user"), ...completion];
}

/** Return a normalized, lower-case role name for a message. */
export function messageRole(message: Message): string {
  const role = typeof message.role === "string" ? message.role.trim().toLowerCase() : "";
  return role || "message";
}

/** Return a display label such as `User` or `Assistant` for a message. */
export function messageRoleLabel(message: Message): string {
  const role = messageRole(message);
  return role.charAt(0).toUpperCase() + role.slice(1);
}

/** Return a message's text content, or null when it is not a plain string. */
export function messageContent(message: Message): string | null {
  return typeof message.content === "string" ? message.content : null;
}
