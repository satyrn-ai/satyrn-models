/**
 * Write Pi's provider payload for the whole session to PI_PAYLOAD_FILE.
 *
 * Remove the docs section from the system prompt and constrainedSampling from the tools,
 * so Pi sends plain tool schemas. The payload is written on the request whose last
 * message is PI_RENDER_TRIGGER_PROMPT, which is then aborted instead of sent.
 */
import { writeFileSync } from 'node:fs';

export default function (pi) {
  pi.on('context_with_system', event => {
    const [system, ...rest] = event.messages;
    const { docs, ...sections } = system.sections;
    const toolsAdded = system.toolsAdded.map(({ constrainedSampling, ...tool }) => tool);
    return { messages: [{ ...system, sections, toolsAdded }, ...rest] };
  });

  pi.on('before_provider_request', (event, ctx) => {
    const lastMessage = event.payload.messages.at(-1);
    if (lastMessage.content?.[0]?.text !== process.env.PI_RENDER_TRIGGER_PROMPT) return;
    writeFileSync(process.env.PI_PAYLOAD_FILE, JSON.stringify(event.payload, null, 1));
    ctx.abort();
  });
}
