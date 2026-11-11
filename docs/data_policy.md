# Data Policy and Compliance

How the YouTube Niche Intelligence platform complies with the
[YouTube API Services Terms of Service](https://developers.google.com/youtube/terms/api-services-terms-of-service)
and [Developer Policies](https://developers.google.com/youtube/terms/developer-policies).

> **Status:** reviewed 2026-11-11 against the policies in effect at that date
> (latest revision-history entry: 1 June 2026, derived-metrics policy update).
> This is an engineering reading of the policy text, not legal advice.
> Re-check the [revision history](https://developers.google.com/youtube/terms/revision-history)
> before each major release.

## 1. Classification of our data

The pipeline calls `search.list`, `videos.list` and `channels.list` with an
**API key** (no OAuth). All responses are therefore **Non-Authorized Data**:
*"API Data accessible by an API Client without User Credentials"* (Developer
Policies, Section IV).

## 2. Rules that constrain the design

| # | Rule | Section | Impact |
|---|---|---|---|
| R1 | Statistics (views, likes, subscriber and comment counts) from Non-Authorized Data must not be stored *"for more than 30 days"* | III.E.4.b | No long-term snapshot history of statistics |
| R2 | Other Non-Authorized Data (titles, descriptions, channel names, IDs) may be stored *"not longer than 30 calendar days"*, then deleted or refreshed. No exemption for IDs was found | III.E.4.d | 30-day retention on all RAW YouTube data |
| R3 | Stored data must be kept reasonably consistent with current data, and user-facing views must show the most up-to-date data; historical data may be shown if *"presented accurately in context of time"* | III.E.4.e–f | Dashboards default to latest snapshot; trends labelled with dates |
| R4 | Must not *"access or use API Data to create new or derived data or metrics"*; e.g. a score that factors in views or likes | III.E.4.h | **No opportunity scores computed from API data** by default |
| R5 | Must not aggregate API Data except across channels of the same content owner | III.E.2.a | Cross-channel benchmarks are restricted |
| R6 | Must not use API Data to gain insights into YouTube's usage, revenue or business | III.E.2.b | No "state of YouTube" analysis |
| R7 | Must not sell, redistribute or sublicense API Data (part of "YouTube API Services") | III.G.1.a–b | **No YouTube data in the public repo**; no selling insights derived from it |
| R8 | Must not embed API credentials in open-source projects | III.D.1.d(4) | Keys only in `.env` (already gitignored) |
| R9 | Show that YouTube is the source of YouTube content; disclose non-YouTube metrics as *"not from YouTube"* | III.F.2.a, III.E.4.h | Attribution and labelling in dashboards |
| R10 | API clients with users must link to the YouTube ToS and require a privacy policy that links to the Google Privacy Policy | III.A.1–2 | README links; applies fully if the tool is ever offered to others |
| R11 | No scraping YouTube | III.E.6 | API only |
| R12 | On termination, delete all API Data and certify on request | ToS 24.3 | Deletion must be easy and complete |

The [Developer Policies Guide](https://developers.google.com/youtube/terms/developer-policies-guide)
lists, as **not allowed** without approval: custom channel "scores" from
averages or ratios, ranking channels against each other, merging API data
with other data, and inferring a video's category. It lists simple arithmetic
(sums, averages, "top viewed videos sorted by views") as acceptable.

There is **no carve-out for internal or personal use**: the rules apply to a
tool built for our own channel business just as they would to a product.

## 3. The derived-metrics route

The [derived-metrics policy](https://developers.google.com/youtube/terms/derived-metrics-policy)
lets **audited developers with analytics use cases** apply (through the quota
extension / API Compliance Audit form, "Analytics & Reporting") to:

- store statistics and derived metrics for **up to 36 months** (titles,
  descriptions etc. remain at 30 days);
- compute custom channel scores, rankings and comparisons;
- show financial projections, *"clearly presented as third-party estimates"*.

Derived metrics must be clearly distinguished from YouTube-sourced metrics.

**Open question:** the amendment explicitly changes the storage rules
(III.E.4.b–d). The text does not explicitly say it overrides the cross-channel
aggregation rule (III.E.2.a). Confirm with YouTube in the application before
relying on it.

## 4. Compliance design

The platform is split into two clearly separated data domains:

| Domain | Source | Retention | Allowed processing |
|---|---|---|---|
| **YouTube API data** | `RAW` schema, from the API | Rolling **30 days**, enforced by the pipeline | Cleaning, typing, current-state reporting, simple arithmetic allowed by the policy guide |
| **Niche intelligence data** | Synthetic data and independent non-YouTube sources, with documented assumptions | Unrestricted | Opportunity scoring, monetisation scenarios, rankings |

Controls:

1. **Retention job.** Each pipeline run deletes RAW rows older than 30 days
   (configurable via `YOUTUBE_RETENTION_DAYS`, hard maximum 30 unless an
   approved derived-metrics use case raises it for statistics only).
   dbt models over YouTube data are views or full rebuilds, so nothing derived
   outlives the RAW rows.
2. **No scores from API data.** The scoring engine reads only from the niche
   intelligence domain. dbt enforces this by keeping the two domains in
   separate model folders and sources.
3. **Provenance.** Every mart row carries a `DATA_SOURCE` value (`youtube_api`,
   `synthetic` or the external source name). Dashboards label non-YouTube
   metrics *"Not from YouTube - estimate"*.
4. **Public repository.** Contains code, DDL and **synthetic** sample data
   only. Screenshots are produced from synthetic data. No API data is
   committed or published.
5. **Attribution.** Dashboards and README credit "YouTube Data API" as the
   source and link to the YouTube ToS and Google Privacy Policy.
6. **Monetisation figures** are scenario estimates from documented
   assumptions, never presented as any channel's actual earnings.

## 5. Quota

Default allocation (subject to change): **100 `search.list` calls per day**,
100 `videos.insert` calls, and **10,000 units per day** for other endpoints,
where `videos.list`, `channels.list` and `playlistItems.list` cost 1 unit per
call. Quotas reset at midnight Pacific Time. Every call, including invalid
ones, costs at least one unit. More quota requires an API Compliance Audit.

Implication: search is the bottleneck (about 100 keyword-pages per day).
Enrichment (50 IDs per call) is cheap.
