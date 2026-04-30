

# Workday API Notes

## Red Hat Pilot

Board page:

- https://redhat.wd5.myworkdayjobs.com/en-US/jobs/jobs

Example job detail page:

- https://redhat.wd5.myworkdayjobs.com/en-US/jobs/jobs/details/Software-Engineer_R-056095-1

Listings API endpoint:

- `POST https://redhat.wd5.myworkdayjobs.com/wday/cxs/redhat/jobs/jobs`

Validated on 2026-04-27:

- The listings API responds with JSON using only a standard POST request with `Content-Type: application/json` and `Accept: application/json`.
- No cookie was required for the initial Red Hat listings request.
- A minimal payload of `{"appliedFacets":{},"limit":3,"offset":0,"searchText":""}` returned `200 OK` and job postings.
- The response included `total`, `jobPostings`, and `facets`, which is enough for a first-pass crawler integration.

Example response shape from Red Hat:

```json
{
	"total": 339,
	"jobPostings": [
		{
			"title": "Software Engineer",
			"externalPath": "/job/Raleigh/Software-Engineer_R-056095-1",
			"locationsText": "Raleigh",
			"postedOn": "Posted Today",
			"remoteType": "Hybrid",
			"bulletFields": ["R-056095"]
		}
	],
	"facets": [
		{
			"facetParameter": "a",
			"descriptor": "Country",
			"values": [
				{
					"descriptor": "United States of America",
					"id": "bc33aa3152ec42d4995f4791a106ed09",
					"count": 89
				}
			]
		}
	]
}
```

## What The Jobs-Page JavaScript Is Doing

The JavaScript embedded on the board page is bootstrap code for Workday's candidate-experience frontend. It does not itself contain the job listings. Its main job is to configure and load the real Workday application bundle.

The important fields in `window.workday` are:

- `tenant: "redhat"`: the Workday tenant identifier.
- `siteId: "jobs"`: the site or board identifier.
- `locale: "en-US"` and `requestLocale: "en-US"`: locale routing and API context.
- `appName: "cxs"`: candidate-experience application namespace used in the API path.
- `clientOrigin` and `cdnEndpoint`: where the frontend assets are loaded from.
- `token`: frontend bootstrap state for the Workday app. It may matter to browser behavior, but it was not needed for the initial listings API call.

After setting `window.workday`, the page script:

1. Loads shared vendor JavaScript.
2. Loads the Workday jobs frontend bundle, usually `cx-jobs.min.js`.
3. Lets that bundle render the listings UI and route between board and detail pages.
4. The frontend bundle then calls the JSON API endpoints under `/wday/cxs/...` to retrieve listings and other structured data.

So the page is a JavaScript shell around an API-backed application. For crawler support, the important surface is the JSON API, not the browser bundle.

## How Listings And Detail URLs Relate

The jobs board needs a list of current postings first. That list comes from the listings API, not from scraping anchor tags out of the initial HTML shell.

For Red Hat, the API returns an `externalPath` such as:

- `/job/Raleigh/Software-Engineer_R-056095-1`

The browser-facing detail route the user sees can also appear in a more explicit form such as:

- `/en-US/jobs/jobs/details/Software-Engineer_R-056095-1`

Both URL styles resolved successfully in a basic HTTP check on 2026-04-27, which means Workday may support more than one public route for the same job. For implementation, treat `externalPath` as a routable URL component but verify and normalize the final public URL pattern before persisting matched jobs.

The current planning implication is:

- We do not need to discover each job URL from browser click handling.
- We do need to fetch the paginated listings payload first, then derive or confirm the public job URL for each returned posting.

## Detail Retrieval Pattern

Validated on 2026-04-27 against Red Hat job `R-056095`:

- `https://redhat.wd5.myworkdayjobs.com/en-US/jobs/jobs/details/Software-Engineer_R-056095-1`
- `https://redhat.wd5.myworkdayjobs.com/en-US/jobs/job/Raleigh/Software-Engineer_R-056095-1`

Both public detail routes returned `200 OK` and exposed the same core job content in the HTML response.

What is present directly in the HTML head:

- canonical URL
- Open Graph title
- Open Graph description containing the full job description text
- JSON-LD `JobPosting` payload with structured fields such as:
	- `title`
	- `description`
	- `identifier.value`
	- `datePosted`
	- `validThrough`
	- `employmentType`
	- `jobLocation`
	- `applicantLocationRequirements`
	- `jobLocationType`
	- `hiringOrganization`

This means the first-pass detail-fetch strategy can be:

1. Fetch listings from the `/wday/cxs/{tenant}/{site}/jobs` endpoint.
2. Build or normalize a public detail URL for each matched job.
3. Fetch the public detail HTML for matched jobs only.
4. Extract the structured `JobPosting` JSON-LD block when present.
5. Fall back to Open Graph tags if JSON-LD is absent on another tenant.

For Red Hat specifically, the detail page is already good enough to retrieve a full description without discovering another JSON detail endpoint.

## Detail Retrieval Implications

- For matching and initial screening, the listings API remains the right source of truth.
- For full descriptions, the public detail page may be simpler and more stable than trying to reverse-engineer a second internal API call.
- The first Workday implementation should therefore avoid blocking on a hidden detail API unless a target tenant fails to embed JSON-LD or full Open Graph content.
- If a future tenant does not expose enough detail in the public HTML, that is when we should inspect the browser network calls for a secondary detail endpoint.

## Request Pattern

Example request captured from the browser:

```http
POST /wday/cxs/redhat/jobs/jobs
Accept: application/json
Content-Type: application/json
```

Example payload with filters:

```json
{
	"appliedFacets": {
		"a": ["bc33aa3152ec42d4995f4791a106ed09"],
		"c": ["48e76bf7cb5510011a9542195ab40001"]
	},
	"limit": 20,
	"offset": 0,
	"searchText": "python"
}
```

Observed payload fields:

- `appliedFacets`: optional filter buckets. Red Hat exposes facet metadata in the response, so later filtering can be driven from returned IDs rather than hardcoded guesses.
- `limit`: page size.
- `offset`: pagination offset.
- `searchText`: free-text search.

For the first implementation pass, the crawler should start with:

- empty `appliedFacets`
- a stable `limit`
- `offset` pagination until the returned page size is less than `limit`
- empty `searchText` unless we intentionally want server-side narrowing

## Red Hat-Specific Implementation Notes

- Tenant: `redhat`
- Site ID: `jobs`
- Locale root: `/en-US/jobs/jobs`
- API root: `/wday/cxs/redhat/jobs/jobs`
- Example job id from `bulletFields`: `R-056095`

This makes Red Hat a good initial test target because:

- the board shell exposes tenant and site identifiers clearly
- the JSON listings endpoint is easy to derive
- the endpoint responds without browser automation
- the response includes facet metadata that can inform later location filtering

## Second Tenant Check: Silicon Labs

Board page:

- https://silabs.wd1.myworkdayjobs.com/en-US/SiliconlabsCareers/jobs

Example job detail page:

- https://silabs.wd1.myworkdayjobs.com/en-US/SiliconlabsCareers/details/Lead-Applications-Engineer---WiFi--NPI-Apps-_20821-1

Derived listings API endpoint:

- `POST https://silabs.wd1.myworkdayjobs.com/wday/cxs/silabs/SiliconlabsCareers/jobs`

Validated on 2026-04-27:

- The board page uses the same Workday bootstrap pattern as Red Hat.
- `window.workday` exposed `tenant: "silabs"`, `siteId: "SiliconlabsCareers"`, and `appName: "cxs"`.
- A minimal JSON POST to the derived listings API returned `200 OK` with `total`, `jobPostings`, and `facets`.
- The response shape matched the Red Hat pattern closely enough for shared crawler code.
- The public detail page also exposed a full `og:description` and a JSON-LD `JobPosting` block containing the full job description.

Example listing payload shape from Silicon Labs:

```json
{
	"total": 64,
	"jobPostings": [
		{
			"title": "Lead Customer Applications Engineer – WiFi (NPI & Customer Engagement)",
			"externalPath": "/job/Hyderabad/Lead-Applications-Engineer---WiFi--NPI-Apps-_20821-1",
			"locationsText": "Hyderabad",
			"postedOn": "Posted 5 Days Ago",
			"bulletFields": ["20821"]
		}
	],
	"facets": [
		{
			"facetParameter": "locationMainGroup",
			"values": [
				{
					"facetParameter": "locationCountry",
					"descriptor": "Location Country"
				},
				{
					"facetParameter": "locations",
					"descriptor": "Locations"
				}
			]
		}
	]
}
```

## What Generalizes Across Red Hat And Silicon Labs

- The board page is still a JavaScript shell with a `window.workday` bootstrap object.
- The listings API still follows `/wday/cxs/{tenant}/{siteId}/jobs`.
- The listings endpoint still works with a simple JSON POST using standard headers.
- The listings response still provides enough information to enumerate jobs and derive public detail routes.
- The public detail page still exposes the full description in both Open Graph metadata and JSON-LD `JobPosting`.

## What Varies Across Tenants

- Host shard can vary, for example `wd5` for Red Hat and `wd1` for Silicon Labs.
- The site ID can be a simple token like `jobs` or a branded token like `SiliconlabsCareers`.
- Canonical public URLs can differ slightly:
	- Red Hat canonicalized to `/en-US/Jobs/job/Software-Engineer_R-056095-1`
	- Silicon Labs canonicalized to `/en-US/SiliconLabsCareers/job/Lead-Applications-Engineer---WiFi--NPI-Apps-_20821-1`
- `externalPath` can include a location segment even when the canonical URL removes or rearranges it.
- Some listings include `remoteType`; others may omit it and rely more heavily on facet metadata and location text.

The implementation consequence is that the crawler should:

1. derive the listings API from the resolved board URL and bootstrap config
2. use the public detail page as the first detail source
3. treat canonical URL extraction from the detail page as the most reliable persisted job URL
4. not hardcode a single public URL template from `externalPath` alone

## First-Pass Crawler Requirements For Workday

1. Resolve a Workday board root with tenant and site ID.
2. Derive the listings API endpoint.
3. Fetch all pages through `offset` pagination.
4. Normalize each posting into shared fields:
	 - company name
	 - board type
	 - source board URL
	 - job id
	 - title
	 - public job URL
	 - location text
	 - remote type
5. Reuse existing title-family matching.
6. Add a Workday-aware location filter that can use both `locationsText` and `remoteType`.
7. Persist ATS type in cache records so a company can move from `non_greenhouse` research state to resolved `workday` state.
8. Prefer canonical URL extraction from the public detail page over a single hardcoded `externalPath` URL builder.

## Implemented In This Repo

As of 2026-04-27, the crawler now has a production first pass for Workday-backed boards.

- Workday crawling logic lives in `ats/workday.py`.
- Shared ATS dataclasses live in `ats/models.py`.
- Shared ATS config loading now lives in `ats/config.py`.
- Supported Workday tenants are configured in `workday_board_hints.json` instead of being hardcoded in the crawler.
- Matched detail pages are fetched from the public HTML page and parsed from JSON-LD `JobPosting`, with Open Graph fallback.
- Detail fetches now retry a `/details/<job-slug>` route when the initial `externalPath`-derived public URL fails.

Validated tenants and counts from 2026-04-27:

- Red Hat: 339 jobs scanned, 37 matches.
- Silicon Labs: 64 jobs scanned, 0 Austin/US-remote matches.
- 3M: 581 jobs scanned, 11 matches.
- Amgen: 1309 jobs scanned, 3 matches.

## Open Questions

- Is the public detail page canonical link always present and stable enough to use as the persisted Workday job URL across tenants?
- Do most Workday tenants expose full descriptions in JSON-LD and Open Graph tags the way Red Hat does, or will some require a second detail API lookup?
- How often will tenant or site IDs need a manual hint instead of heuristic discovery?
- Can remote and country filters be derived reliably enough from returned facet metadata to keep Austin and US-remote filtering consistent with the Greenhouse workflow?