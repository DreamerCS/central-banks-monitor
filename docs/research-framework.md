# From central-bank communication to a macro research decision

This is an analytical checklist, not a trading signal. The user-supplied `Prompt.docx` remains private and governs the **source-grounded reading** of reports, speeches and other central-bank publications. For a speech or policy statement, adapt its report-specific word counts and attribution to the document, without removing its evidence, uncertainty and follow-up-question requirements. Reference books guide questions to ask; they are not a source of factual claims about the document being read.

## 1. Read and classify the communication

Retain the source URL, institution, jurisdiction, document type (speech, testimony, decision, minutes, forecast, research), speaker and role, original language and translation status, delivery time, publication time, revision, and full text hash. Record whether the communication is monetary policy, supervision, payments, financial stability or another topic; do not score every central-bank speech as a rate signal.

For each source, answer: What changed versus the appropriate prior communication? Which claims are the speaker's, which are quotations or market expectations? Which evidence, charts and caveats support or weaken the view? What would change the investment judgment? Keep citations and uncertainty. A model should produce **separate** source-only analysis and ranked unanswered research questions under the supplied prompt. Analyst review precedes release.

## 2. Economic mechanism and market hypothesis

Use the reference books as lenses, not quotations to import into the summary:

| Reference | Useful analytical checks | Relevant market channel |
| --- | --- | --- |
| Willer & Saunders, *Trading Global Macro Markets*, especially chapters on the business cycle and rates | Cycle state, leading versus lagging evidence, path versus pricing, curve and supply | Front-end rates, curve, FX and risk assets |
| Challe, *Macroeconomic Fluctuations and Policies*, chapters on monetary policy, expectations, forward guidance and asset purchases | Demand versus supply shock, credibility, policy transmission and lags | Expected short rates and term premia |
| Mehrling, *The New Lombard Street*, chapters on dealers and funding versus market liquidity | Collateral, dealer balance sheets, liquidity stress and swap channels | Funding spreads, Treasury liquidity and cross-currency basis |
| Eichengreen, *Globalizing Capital* | Exchange-rate regime and external constraints | FX reaction and policy space |
| Kurlat, *A Course in Modern Macroeconomics*; course macro notes | Expectations, policy regime and model assumptions | Scenario discipline |
| Allen, *Global Economic History*; DeLong, *Slouching Towards Utopia* | Structural and historical context | Longer-horizon hypotheses, not a mechanical event signal |

Before interpreting a speech, state the sign and horizon **conditional on the policy surprise**. A hawkish tone may coexist with falling yields if it was already priced, if the growth outlook deteriorated, or if a different release dominated. Separate sentiment, expectation, surprise, and realised price change. Track the policy path and term premium separately where data permit. Specify the instrument and tenor rather than treating all rates as one asset.

## 3. Scoring and aggregation

The supplied research prompt has **no numeric hawkish/dovish scale**. Integrate the team's validated scorer as a separate versioned stage. Store `score_level`, `score_shift`, their scale, confidence, evidence citations, comparison document, model version, review status and topic relevance. Calibrate by jurisdiction and language; benchmark against human annotations. Do not combine incomparable scores or interpret a raw score as a market surprise. A composite index needs a declared sample, weighting, calendar, revision policy and uncertainty bands.

## 4. Market measurement

For every asset, record provider, symbol, quote side, unit, frequency, licence, UTC observation time and freshness. For intraday event analysis use the verified **first public release time**, compare predeclared windows and report exact before/after observations. Exclude or flag missing timing, holidays, stale quotes, simultaneous macro releases and scheduled policy meetings. Report rates in basis points, FX in a clearly specified quote direction and assets in appropriate price/return units. Observed change is descriptive; causal attribution needs controls.

The site's U.S. Treasury benchmark uses the Treasury's **daily par yield curve feed**, refreshed by the deployment workflow after U.S. business days. It is a dated context series. It cannot answer a one-hour speech event question. For minute-level 2Y, FX, equity and commodity reactions, connect a licensed timestamped provider server-side. The existing browser CSV calculator accepts user-supplied observations locally while that integration is pending.

## 5. Research output

Keep separate blocks for (a) source-only summary and cited claims, (b) scoring with calibrated evidence, (c) market before/after measurement, (d) interpretation with competing explanations, and (e) trade hypothesis, horizon, catalyst, risk and invalidation. A trade idea is an analyst inference, not a model output. Never publish licensed full texts, private reports, supplied books, API keys or the team's model in this public repository.
