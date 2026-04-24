#!/usr/bin/env python3
"""
Test script for calling Workday job board API directly.

This demonstrates how to bypass JavaScript-rendered pages by calling
the underlying API that Workday uses to load job listings.

Workday is a common Applicant Tracking System (ATS) used by many large
companies. Once you understand the API pattern for one Workday instance,
you can adapt it for other companies using Workday.
"""

import json
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


def fetch_workday_jobs(
    base_url: str,
    search_text: str = "",
    limit: int = 20,
    offset: int = 0,
    applied_facets: dict | None = None,
) -> dict:
    """
    Fetch jobs from a Workday API endpoint.
    
    Args:
        base_url: The Workday API base URL (e.g., 
                 "https://company.wd5.myworkdayjobs.com/wday/cxs/company/jobs/jobs")
        search_text: Keyword to search for (e.g., "python", "software engineer")
        limit: Maximum number of results to return in one page
        offset: Pagination offset (0 for first page, 20 for second if limit=20, etc.)
        applied_facets: Optional filters like location, job type, etc.
                       Format: {"a": ["facet_id"], "c": ["category_id"]}
    
    Returns:
        Dictionary containing the JSON response from Workday API
    
    Raises:
        HTTPError: If the API request fails
        URLError: If there's a network issue
    """
    # Build the request payload
    # This mimics what the browser sends when you search on the Workday job page
    payload = {
        "appliedFacets": applied_facets or {},  # Filters like remote/onsite, location, etc.
        "limit": limit,                          # How many results per page
        "offset": offset,                        # Where to start (for pagination)
        "searchText": search_text,               # Search keyword(s)
    }
    
    # Convert Python dict to JSON string for the request body
    payload_json = json.dumps(payload).encode("utf-8")
    
    # Create the HTTP request
    # Workday APIs are typically POST requests with JSON payloads
    request = Request(
        base_url,
        data=payload_json,  # The search parameters
        method="POST",
    )
    
    # Set required headers
    # These tell the server we're sending and expecting JSON
    request.add_header("Content-Type", "application/json")
    request.add_header("Accept", "application/json")
    
    # Optional: Add a User-Agent to identify the client
    # Some servers may block requests without a User-Agent
    request.add_header(
        "User-Agent",
        "job-search-api-client/1.0 (+polite bot for personal job search)"
    )
    
    # Make the request and parse the JSON response
    try:
        with urlopen(request, timeout=30) as response:
            # Read the response body (bytes) and decode to string
            response_data = response.read().decode("utf-8")
            # Parse JSON string into Python dictionary
            return json.loads(response_data)
    except HTTPError as e:
        print(f"HTTP Error {e.code}: {e.reason}", file=sys.stderr)
        raise
    except URLError as e:
        print(f"URL Error: {e.reason}", file=sys.stderr)
        raise


def filter_jobs_by_keywords(jobs: list[dict], keywords: list[str]) -> list[dict]:
    """
    Filter job listings to only those matching target keywords in the title.
    
    Args:
        jobs: List of job dictionaries from Workday API response
        keywords: List of keywords to match (case-insensitive)
                 Examples: ["python", "software engineer", "developer"]
    
    Returns:
        Filtered list of jobs where the title contains at least one keyword
    """
    filtered = []
    
    for job in jobs:
        # Get the job title (lowercase for case-insensitive matching)
        title = job.get("title", "").lower()
        
        # Check if any of our target keywords appear in the title
        if any(keyword.lower() in title for keyword in keywords):
            filtered.append(job)
    
    return filtered


def main():
    """
    Test the Workday API with Red Hat's job board.
    
    This example searches for Python-related jobs and prints the results.
    """
    # Red Hat's Workday API endpoint
    # Pattern: https://{company}.wd5.myworkdayjobs.com/wday/cxs/{company}/{site-name}/jobs
    api_url = "https://redhat.wd5.myworkdayjobs.com/wday/cxs/redhat/jobs/jobs"
    
    # Search parameters
    search_keyword = "python"
    
    # Optional: Apply facets (filters) found in the browser URL
    # These IDs come from the URL parameters when you filter on the website
    # Example: ?a=facet_id filters by attribute, ?c=category_id filters by category
    # For now, we'll use the facets from the example Red Hat URL
    facets = {
        "a": ["bc33aa3152ec42d4995f4791a106ed09"],  # Likely "Remote" filter
        "c": ["48e76bf7cb5510011a9542195ab40001"],  # Likely "USA" location filter
    }
    
    print(f"Fetching jobs from Red Hat Workday API...")
    print(f"Search keyword: '{search_keyword}'")
    print(f"Applied facets: {facets}")
    print("-" * 80)
    
    try:
        # Make the API call
        response = fetch_workday_jobs(
            base_url=api_url,
            search_text=search_keyword,
            limit=20,           # Get 20 results (default page size)
            offset=0,           # Start from first result
            applied_facets=facets,
        )
        
        # The response structure typically has a "jobPostings" key
        # containing the list of jobs
        job_postings = response.get("jobPostings", [])
        
        if not job_postings:
            print("No jobs found matching the search criteria.")
            return
        
        print(f"Found {len(job_postings)} jobs total")
        print("=" * 80)
        
        # Define our target job title keywords
        # These are the types of roles we're interested in
        target_keywords = [
            "software engineer",
            "developer",
            "python",
            "backend",
            "data engineer",
        ]
        
        # Filter to only jobs matching our keywords
        matched_jobs = filter_jobs_by_keywords(job_postings, target_keywords)
        
        print(f"\nFiltered to {len(matched_jobs)} jobs matching keywords: {target_keywords}")
        print("=" * 80)
        
        # Display the filtered results
        for idx, job in enumerate(matched_jobs, 1):
            title = job.get("title", "Unknown Title")
            locations = job.get("locationsText", "Location not specified")
            remote_type = job.get("remoteType", "")
            posted = job.get("postedOn", "Date unknown")
            external_path = job.get("externalPath", "")
            job_id = job.get("bulletFields", [""])[0] if job.get("bulletFields") else ""
            
            # Build the full job URL
            # Pattern: https://{company}.wd5.myworkdayjobs.com/en-US/{site-name}{externalPath}
            full_url = f"https://redhat.wd5.myworkdayjobs.com/en-US/jobs{external_path}"
            
            print(f"\n{idx}. {title}")
            print(f"   Job ID: {job_id}")
            print(f"   Location: {locations} ({remote_type})")
            print(f"   Posted: {posted}")
            print(f"   URL: {full_url}")
        
        # Note: Workday APIs support pagination
        # To get more results, increment the offset parameter:
        # - First 20 jobs: offset=0
        # - Next 20 jobs: offset=20
        # - Next 20 jobs: offset=40
        # Continue until response has fewer jobs than the limit
        
        print("\n" + "=" * 80)
        print("API test successful!")
        print("\nTo get more results, call again with offset=20, then offset=40, etc.")
        
    except (HTTPError, URLError) as e:
        print(f"Failed to fetch jobs: {e}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON response: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
