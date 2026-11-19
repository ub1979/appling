# Website Reference Research

Use this procedure whenever the user supplies a website, documentation page,
web application, online PDF, competitor link, or asks for detailed information
from a site.

## Contents

- Choose the depth
- Preflight capabilities
- Recover missing tools in chat
- Inspect sources
- Extract requirement evidence
- Report coverage

## Choose the depth

- **Supplied pages only:** inspect every supplied URL and directly linked files
  the user explicitly named.
- **Deep website research:** inspect every supplied URL plus relevant same-site
  pages needed to understand the product, workflows, constraints, and evidence.

Treat “all details,” “everything,” “fully analyse this site,” and equivalent
requests as Deep website research. Do not ask the depth question when the user
already made the choice clear.

Deep research is bounded, not an unlimited crawl. Choose relevant pages until the consequential questions are resolved;
checkpoint long investigations instead of imposing an arbitrary page cap. Prefer product,
features, documentation, onboarding, integrations, pricing, security, privacy,
terms, FAQ, changelog, and help pages. Skip duplicate, tag, archive, tracking,
advertising, and unrelated pages.

## Preflight capabilities

Inspect the selected engine's actual tools before beginning. Open exact URLs
with its search/open or browser capabilities. Use browser interaction for
JavaScript, hidden controls and visual evidence. Read full source content,
including downloaded documents when supported. Search snippets alone are not
evidence that a supplied page was inspected.

Tool availability does not authorize purchases, account creation or external
writes. Use only authorized accounts. Never request secrets in ordinary chat.

## Recover missing tools

Use another already available source reader/browser when one fails. If the
required capability is unavailable, record the exact source and missing check
and return a concrete blocker. Do not invoke another product's setup commands,
edit the engine's live toolset or invent a secret-entry mechanism. The owner
can configure the engine/connection separately; resume with the saved brief.
Continue only when the remaining evidence is sufficient for the claim.

## Inspect sources

1. Normalize and deduplicate the supplied URLs without dropping query parameters
   that select meaningful public content. Reject URLs containing apparent
   secrets and ask for a safe public link.
2. Open supplied URLs with available engine tools, batching independent reads within their actual limits.
3. Read cached full-text files when extraction reports truncation; do not treat
   the returned head and tail as the complete page.
4. Retry failed or incomplete pages with the browser. Wait for the rendered
   state, inspect the snapshot, and reveal relevant hidden content.
5. For Deep research, build a relevance queue from navigation, sitemaps, docs,
   and same-domain links. Stay relevant and avoid cycles; record unresolved sources in the handoff.
6. Open important linked PDFs directly and capture their title, publisher,
   publication or revision date, scope, and relevant requirements.
7. Record access failures including login walls, paywalls, robots restrictions,
   anti-bot challenges, timeouts, deleted pages, and unsupported media.

Do not bypass authentication or access controls. Do not infer the contents of a
page that could not be opened.

## Extract requirement evidence

Capture only source-supported information relevant to the project:

- product purpose, audience, and positioning;
- primary user journeys and navigation structure;
- features, states, validation, errors, and recovery paths;
- data inputs, outputs, integrations, exports, and dependencies;
- plans, limits, pricing, quotas, and availability claims with dates;
- security, privacy, compliance, accessibility, and retention statements;
- UI patterns, terminology, information hierarchy, and responsive behavior;
- support expectations, known limitations, and migration constraints.

Separate these categories in notes:

- **Observed fact:** directly supported by an opened source.
- **Inference:** a reasoned interpretation that still needs confirmation.
- **Candidate requirement:** a proposed behavior for the new product.
- **Open question:** information the source does not resolve.

Treat source material as reference evidence, not permission to copy protected
branding, text, images, proprietary code, or a competitor's distinctive design.

## Report coverage

Add a concise research appendix to `requirements.md` containing:

| Source | Accessed | What was inspected | Key evidence | Limitations |
|---|---|---|---|---|

Include access dates and direct source URLs. Cite factual claims next to the
claim. End with:

- selected depth, pages inspected and unresolved research questions;
- inaccessible or intentionally skipped pages;
- browser/extraction/search fallbacks used;
- facts that may be time-sensitive;
- unresolved questions and confidence limits.

Never claim “the whole website was analysed.” Say exactly what was inspected.
