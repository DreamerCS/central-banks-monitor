# Analysis and index integration contract

This file defines the hand-off for the team's existing scoring model and a future document analysis service. The public site intentionally does not bundle model weights, private prompts, licensed reports, API keys or market data.

## Report analysis

Use the user-supplied `Prompt.docx` as the governing instruction for **sell-side research reports**. The model must receive the complete source document, including chart images, tables, footnotes and appendices. It should return a report-based summary (approximately 500–800 words), followed by 3–5 ranked questions for further research (approximately 200–350 words), with page/chart references and any coverage limitation. Do not blend later market data or external sources into the report summary. Keep the prompt file private unless the owner explicitly approves publication.

Proposed result fields: `document_id`, `report_date`, `title`, `summary`, `questions[]` (rank, question, known, uncertain, investment_relevance, evidence_needed, next_source_type), `citations[]` (page, chart/table), `unreadable_sections[]`, `model_version`, `review_status`.

## Speech scoring

The supplied report prompt does not define a numeric hawkish/dovish score. Obtain the Cambridge team's validated scorer and its scale, calibration and benchmark before integrating it. Retain separately:

- `source_url`, `institution_id`, `speaker`, `role`, `speech_title`, `language`, `original_text_hash`;
- `delivered_at_utc`, `published_at_utc`, `timestamp_precision`, `source_timezone`, `embargo_status`;
- `score_level`, `score_shift`, `score_scale`, `comparison_speech_id`, `evidence_passages[]`, `model_version`, `review_status`.

Never infer the market event time from the speech date alone. If release timing is uncertain, exclude the item from intraday event analysis until an analyst resolves it. A speaker's policy stance and the change from an earlier speech are distinct measures. Build the index only from a predeclared, consistent sample of speeches; record inclusions, revisions and missing texts.

## Market data and event windows

For each event and asset (for example, the US two-year Treasury yield), keep the provider, symbol, unit, observation timestamp in UTC, sampling frequency and licence. Define the pre- and post-speech window before inspection. Return the selected timestamps and levels, absolute change, and basis-point change for yields expressed in percentage points. Preserve missing observations as missing; do not backfill through a holiday or stale quote without a documented rule. Record simultaneous macro releases, policy meetings and other confounders. A before/after difference is descriptive and does not establish causation.

The current browser-only CSV calculator follows this narrow rule: choose the closest strictly earlier and strictly later observation within the maximum selected gap. It never uploads the file. The production pipeline should validate data quality, timezone and release time before combining score and price changes.

## Publication gates

Keep source collection, score generation, analyst review and public release as separate states. Publish only reviewed scores and appropriately licensed derived market data. The public directory entry is not evidence of a working feed or a reviewed speech. Keep secrets and any proprietary model on a server-side service, never in GitHub Pages JavaScript.
