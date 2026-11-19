import type { InboxItem } from "../live";

export function questionTarget(inbox: InboxItem[], selected: string): string | undefined {
  const questions = inbox.filter((item) => item.kind === "question");
  return questions.length === 1 ? questions[0].id : questions.find((item) => item.id === selected)?.id;
}

export function composerContext(inbox: InboxItem[], busy: boolean) {
  if (inbox.filter((item) => item.kind === "question").length > 1) return {
    placeholder: "Write your answer to the selected question…",
    hint: "Choose which question to answer above. Your reply goes only to that worker. Enter to send · Shift+Enter for a new line.",
  };
  const targets = inbox.filter((item) => ["question", "prototype", "requirements", "plan"].includes(item.kind));
  if (targets.length === 1) {
    if (targets[0].kind === "question") return {
      placeholder: "Answer Appling’s question…",
      hint: "Sent as your answer to the question above. Picked parts and attachments are included. Enter to send · Shift+Enter for a new line.",
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
