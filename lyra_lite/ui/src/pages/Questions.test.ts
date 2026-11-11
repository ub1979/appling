import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { asksForQuestion, NeedCard } from "./Studio";

describe("question detection", () => {
  it("recognises a question followed by an explanation in the final paragraph", () => {
    expect(asksForQuestion("We’ll target Hermes.\n\nWhat kind of data will you mainly analyse? This helps us choose useful default charts and reports.")).toBe(true);
  });

  it("recognises a question at the end of a reply", () => {
    expect(asksForQuestion("What kind of data will you analyse?")).toBe(true);
  });

  it("ignores questions in earlier paragraphs followed by a completed update", () => {
    expect(asksForQuestion("You asked: Why are sales down?\n\nThe report is ready.")).toBe(false);
    expect(asksForQuestion("Your prototype is being checked.")).toBe(false);
    expect(asksForQuestion("Open the prototype at http://localhost:9200/?preview=1")).toBe(false);
  });
});

describe("requirements question shortcuts", () => {
  function card(kind: string, choices: string[] = []) {
    return renderToStaticMarkup(createElement(NeedCard, {
      item: { id: "question-1", created: 1, kind, question: "Which data?", choices },
      requirementsInterview: true,
      seenPrototype: null,
      onOpenPrototype: () => {},
      onAnswer: () => {},
    }));
  }

  it.each([{ choices: [] }, { choices: ["Sales", "Finance"] }])(
    "offers every shortcut with choices $choices", ({ choices }) => {
    const html = card("question", choices);
    expect(html).toContain("Skip this question");
    expect(html).toContain("Decide for me");
    expect(html).toContain("Use smart defaults");
  });

  it.each(["secret", "approval", "prototype", "requirements"])("keeps shortcuts off the %s checkpoint", (kind) => {
    const html = card(kind);
    expect(html).not.toContain("Use smart defaults");
    expect(html).not.toContain("Skip this question");
  });
});
