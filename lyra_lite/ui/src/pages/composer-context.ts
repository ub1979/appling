import type { InboxItem } from "../live";

export function composerContext(inbox: InboxItem[], busy: boolean) {
  const targets = inbox.filter((item) => ["question", "prototype", "requirements"].includes(item.kind));
  if (targets.length === 1) {
    if (targets[0].kind === "question") return {
      placeholder: "Answer Appling’s question…",
      hint: "Sent as your answer to the question above. Picked parts and attachments are included.",
    };
    return {
      placeholder: "Describe what you want changed…",
      hint: "Sending requests changes and includes your picked parts. Use the approval button above to approve.",
    };
  }
  return {
    placeholder: busy ? "Appling is working — write anyway, it reads this next…" : "Message Appling…",
    hint: inbox.length ? "Use the cards above to answer pending requests. Messages here are queued for the next turn."
      : "Enter to send · Shift+Enter for a new line · drop files here or use 📎",
  };
}
