# Phase 8: optional Job-mode web research

After the Phase 6 base question plan is generated, Job-mode sessions get one optional Gemini call with Google Search grounding. The call has a 15-second wall-clock limit and uses only the job description and selected role; it does not send the candidate resume. It returns at most three supplemental topics. Random and Resume modes do not call this task.

The Gemini provider sends the `google_search` built-in tool through the existing LLM router. Grounded result URLs/titles, model provenance, and fallback provisional status are kept in `config.interview_plan.web_research`. Base plan topics use `source: "resume_jd"`; supplemental topics use `source: "web_research"`. Mixed topics keep the original source and record `question_seed_sources` plus `source_tags` so individual additions remain distinguishable.

Timeouts, provider errors, malformed/empty output, or responses without grounding citations are logged and leave the Phase 6 plan unchanged. Enrichment failures do not change preparation status. No sites are scraped by the application.

The `job_web_research` route uses Gemini 3.8 Flash with Gemini 3.5 Flash-Lite fallback. Google Search grounding must be enabled and available for the configured Gemini project. See [Gemini grounding with Google Search](https://ai.google.dev/gemini-api/docs/google-search) for supported models and API behavior.
