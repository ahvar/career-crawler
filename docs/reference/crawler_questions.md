# Web Crawler Questions and Answers

## What is commonly in a robots.txt file and how does it affect scraping?

### What is robots.txt?
A `robots.txt` file is a plain text file placed at the root of a website (e.g., `https://example.com/robots.txt`) that tells web crawlers which parts of the site they can and cannot access.

### Common Contents of robots.txt

```
User-agent: *
Disallow: /admin/
Disallow: /private/
Allow: /public/

User-agent: Googlebot
Crawl-delay: 1
Disallow: /temp/

Sitemap: https://example.com/sitemap.xml
```

**Key directives:**
- `User-agent`: Specifies which crawler the rules apply to (`*` means all crawlers)
- `Disallow`: URL paths that crawlers should NOT access
- `Allow`: URL paths that crawlers CAN access (overrides Disallow)
- `Crawl-delay`: Minimum seconds to wait between requests
- `Sitemap`: Location of XML sitemap for easier crawling

### How It Affects Scraping

**For Polite Crawlers (like ours):**
- Should respect the rules and not crawl disallowed paths
- Should implement crawl delays as specified
- May choose to not scrape at all if broadly blocked

**Legal/Ethical Considerations:**
- Violating robots.txt is not illegal in most jurisdictions, but:
  - It's considered unethical in the web community
  - May violate a website's Terms of Service
  - Could lead to IP blocking or legal action in some cases
- Respecting robots.txt is a best practice for responsible scraping

**Our Crawler's Behavior:**
- Fetches and parses robots.txt before accessing any page
- Checks if each URL is allowed before fetching
- Logs when URLs are blocked
- Implements rate limiting regardless of robots.txt

---

## Browser Interaction vs Web Crawler Capabilities

### JavaScript-Powered Search Forms

**Your Question:** *"If I navigate to https://careers.hhs.texas.gov/ in the browser and type 'Python' in a search box, I get results. Can a web crawler implement the equivalent action?"*

**Answer:** Not directly with basic HTML crawlers like ours.

**Why the Limitation:**
1. **JavaScript Execution**: The search form likely uses JavaScript to:
   - Capture your input
   - Make an AJAX request to a backend API
   - Dynamically update the page with results
   
2. **Basic Crawlers Can't Execute JavaScript**: Tools like `urllib` (which our crawler uses) only fetch the static HTML. They don't:
   - Execute JavaScript code
   - Handle dynamic DOM updates
   - Simulate user interactions like typing or clicking

3. **What Basic Crawlers See**: When fetching the initial page, they only get the HTML template with empty search boxes, not the dynamic content loaded after interaction.

---

### URL-Based Search Results

**Your Question:** *"What if I pass the URL returned when I search, like: `https://careers.hhs.texas.gov/search/?createNewAlert=false&q=python&optionsFacetsDD_location=...`"*

**Answer:** This depends on how the site is built, and it's often possible!

**When It Works:**
If the search results are **server-side rendered** (meaning the server generates complete HTML based on the URL parameters), then yes:
- Our crawler can fetch that URL directly
- It will receive the HTML page with the Python search results
- It can then extract job listing links from that HTML

**When It Doesn't Work:**
If the search results are **client-side rendered** (JavaScript loads them after the page loads), then:
- The crawler fetches the URL but gets a skeleton page
- The actual results require JavaScript execution to appear
- The crawler won't see the job listings

**How to Test:**
1. Visit the search URL in your browser
2. Right-click → "View Page Source" (not Inspect Element)
3. Search for a job title you see on the page
4. **If you find it** in the raw HTML: ✅ Our crawler can access it
5. **If you don't find it**: ❌ Results are JavaScript-loaded

**For Texas HHS Careers:**
The URL you provided (`https://careers.hhs.texas.gov/search/?q=python&...`) likely works with a basic crawler because:
- Government job sites often use traditional server-side rendering
- The query parameters (`q=python`) suggest server-side processing
- The job listing at `https://careers.hhs.texas.gov/hhscjobs/job/AUSTIN-Senior-RPA-Developer-TX-73301/1373183800/` is probably a real, crawlable page

---

## Solutions for JavaScript-Heavy Sites

If we encounter sites where basic HTML crawling isn't enough, we have options:

### 1. **Headless Browsers** (Most Complete)
Tools like Selenium or Playwright can:
- Execute JavaScript like a real browser
- Fill out forms and click buttons programmatically
- Wait for dynamic content to load
- Extract the final rendered HTML

**Tradeoffs:**
- ✅ Can handle almost any site
- ❌ Much slower (seconds per page vs milliseconds)
- ❌ Higher resource usage (memory, CPU)
- ❌ More complex to implement and maintain

### 2. **API Inspection** (Most Efficient)
Many sites load data via APIs. We can:
- Use browser DevTools Network tab to find the API endpoints
- Call those APIs directly (much faster than rendering pages)
- Parse JSON responses instead of HTML

**Tradeoffs:**
- ✅ Fast and efficient
- ✅ Clean, structured data
- ❌ APIs may be undocumented or change frequently
- ❌ May require authentication or have rate limits
- ❌ Could violate Terms of Service if APIs are "private"

### 3. **Hybrid Approach** (Our Current Strategy)
- Use basic HTML crawling as the default (fast, simple, respects robots.txt)
- Identify specific sites that need special handling
- Provide direct URLs or API endpoints for those cases
- Consider headless browsers only when necessary

---

## Current Crawler Limitations

Based on the code review, our `crawl_gregslist.py` script:

**Can Handle:**
- Static HTML pages with job listings
- Server-side rendered search results (if given the URL)
- Traditional career pages with direct job links
- Standard HTML forms (by constructing URLs manually)

**Cannot Handle:**
- JavaScript-powered search boxes
- Single Page Applications (SPAs) that load content dynamically
- Infinite scroll job boards
- Sites requiring login or CAPTCHA
- External ATS platforms (currently blocked by same-origin check)

**Should Be Improved:**
- Better validation of what constitutes a job listing vs informational page
- Following external ATS links (Workable, Greenhouse, Lever, etc.)
- More sophisticated pattern matching to avoid false positives
- Ability to detect when a "careers page" is actually a redirect to an external ATS

---

## Recommendations

1. **For Government/Public Sector Sites:** Most use traditional HTML and can be crawled with our current tool if we provide the right search URLs.

2. **For Modern Startups:** Many use ATS platforms (Greenhouse, Lever, Workable) which are external domains. We should modify our crawler to follow these specific external links.

3. **For Complex Cases:** Consider building a small list of "known patterns" for popular ATS systems, rather than trying to handle all JavaScript-heavy sites.

4. **Testing Approach:** Always check "View Page Source" to verify if content is in the HTML before investing in headless browser solutions.
