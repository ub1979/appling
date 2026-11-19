import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { asksForQuestion, NeedCard, Composer } from "./Studio";

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

describe("command approval origin", () => {
  it("shows the requesting agent, assigned task and model above the command", () => {
    const html = renderToStaticMarkup(createElement(NeedCard, {
      item: { id: "approval", kind: "approval", created: 1, command: "example command", description: "flagged command",
        requester: { subagent_id: "planner", label: "Task planning", model: "test-model", goal: "Verify invocation syntax" } },
      seenPrototype: null, onOpenPrototype: () => {}, onAnswer: () => {},
    }));
    expect(html).toContain("Task planning");
    expect(html).toContain("test-model");
    expect(html).toContain("Verify invocation syntax");
    expect(html).toContain("Don&#x27;t allow");
  });
});

describe("implementation plan review", () => {
  it("offers a real plan viewer and disables approval until it is opened", () => {
    const html = renderToStaticMarkup(createElement(NeedCard, {
      item: { id: "plan", kind: "plan", created: 1, question: "Actual saved implementation plan", revision: "current" },
      seenPrototype: null, onOpenPrototype: () => {}, onAnswer: () => {},
    }));
    expect(html).toContain("Show implementation plan");
    expect(html).toContain('disabled=""');
    expect(html).not.toContain("Actual saved implementation plan");
  });

});

describe("conversational questions and multiline composer", () => {
  it("renders an ordinary question as chat without a second input or warning card", () => {
    const html = renderToStaticMarkup(createElement(NeedCard, {
      item: { id: "question", kind: "question", created: 1, question: "What should your app do?", choices: ["Track spending"] },
      requirementsInterview: true, onAnswer: () => {}, seenPrototype: null, onOpenPrototype: () => {},
    }));
    expect(html).toContain('class="msg lyra"');
    expect(html).toContain("What should your app do?");
    expect(html).toContain("Track spending");expect(html).toContain("Use smart defaults");
    expect(html).not.toContain("need-card");expect(html).not.toContain("<input");
    expect(html).not.toContain("Appling has a question");
  });
  it("provides a single main textarea with six visible rows", () => {
    const html = renderToStaticMarkup(createElement(Composer, {
      busy: false, inbox: [{ id: "q", kind: "question", created: 1 }], projectId: "test",
      onSend: async () => true, dropped: [], picks: [], onPicksChange: () => {},
    }));
    expect(html).toContain("<textarea");expect(html).toContain('rows="6"');
    expect(html).toContain('aria-label="Message Appling"');expect(html).toContain("Shift+Enter");
  });
  it("lets the user select the worker question while keeping one multiline composer", () => {
    const html = renderToStaticMarkup(createElement(Composer, {
      busy: true, inbox: [
        { id: "frontend", kind: "question", created: 1, question: "[ui] Which layout?" },
        { id: "backend", kind: "question", created: 2, question: "[api] Which database?" },
      ], projectId: "test", onSend: async () => true, dropped: [], picks: [], onPicksChange: () => {},
    }));
    expect(html).toContain("Which question are you answering?");
    expect(html).toContain('value="frontend"'); expect(html).toContain('value="backend"');
    expect(html.match(/<textarea/g)).toHaveLength(1);
    expect(html).toContain("Choose a question first");
  });
});
