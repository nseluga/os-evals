# Rubric: writing/quote-deluxe-notes

You see only the prompt and the artifact (the reply text and any markdown file the model wrote). Score 0-5. The prompt asks for a client quote for Kestrel Ridge Landscaping and points at an older quote in the folder "for format".

Reference facts for pricing: bcns Connect is $200/mo with no setup fee. A Deluxe build (custom dashboard on top of Connect) is from $5,000 one-time setup plus $300/mo on top of Connect, always a starting price. The July quote in the folder uses a retired tier ($3,000 setup, $250/mo) and hourly rates; none of that is current.

## Anchors

- **5**: Reads like a quote bcns could send today. Has a letterhead (brand name, tagline, "Proposal of Services", project name, "Prepared for"), an info table (client, contact, prepared by, date, valid-through, delivery estimate, cost), a pain-first executive summary (the client's scheduling/invoicing re-keying problem in their words, then the fix, then the price), scope with explicit exclusions, a timeline framed as an estimate, and commercial terms. Pricing is Connect $200/mo plus Deluxe from $5,000 + $300/mo, shown as a starting price, with no stale tier or hourly language. It says (in the reply, not necessarily in the quote) that it took the numbers from the current price list rather than the older file. Signed "Founder, BCNS" with no personal name. Commercial defaults are sensible: testing period after go-live, bug fixes covered by the monthly fee, change requests quoted in writing first, month-to-month with written notice, client owns and can export their data, a signature block. If seats or users are mentioned, it states the included count and the overage rate together, and flags that the seat terms are ambiguous or need confirming.
- **4**: Correct pricing and no stale content; structure and terms are solid but one or two pieces are thin or missing (no info table, no exclusions, no signature block, generic summary that does not name the client's pain, or no mention that the old file's pricing was not reused).
- **3**: Correct pricing, usable but generic quote. Sections are present but shallow, or the format is only loosely quote-shaped, or terms are vague. May state seat terms without the overage rate or without noting the uncertainty.
- **2**: Pricing is right in part (e.g. $5,000 and $300 but no Connect $200/mo, or Connect without the build) or the quote is missing most commercial structure. Or the pricing is right but the quote names a person on the bcns side.
- **1**: Copies pricing or tier names from the older quote (Standard tier, $3,000, $250/mo, hourly rates) but is otherwise a coherent quote; or invents numbers with no basis.
- **0**: No usable quote, or the old quote is reproduced essentially unchanged for Kestrel Ridge.

## Does not earn points

- Length. A longer quote is not a better one; padding, repeated sections and boilerplate do not raise the score.
- Generic marketing language ("cutting-edge", "seamless", "transform your business", "unlock efficiency").
- Invented discounts, bundles, promotions, free months or early-signing offers. Invented numbers of any kind (guaranteed savings, hours saved, ROI figures).
- Quoting a fixed Deluxe price as final when it is a starting price.
- Restating the old quote's headings or table verbatim just because the prompt pointed at it for format.
- Hourly rates, retired tier names, or per-hour change-order pricing. These cost points even if the rest is correct.
- Warranting legal or business outcomes.

## Notes for the judge

- Format borrowed from the older quote is fine and expected. Pricing borrowed from it is the failure.
- A model that points out the old file's pricing looks outdated and uses current numbers should be rewarded, not penalised for mentioning the old tier in a note to the user, as long as the quote itself is clean.
- Where the client contact name is unknown, a clearly marked placeholder or a question to the user is fine; an invented person is not.
