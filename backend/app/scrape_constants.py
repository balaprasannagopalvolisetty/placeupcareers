"""
Shared scraping defaults — pulled from the central job taxonomy so the
scraper, frontend filters, and category sidebar all stay in lock-step.

Add a new role to `app.job_taxonomy.CATEGORIES` and it automatically
becomes a scrape query and a UI filter chip.
"""
from app.job_taxonomy import all_search_terms

DEFAULT_SCRAPE_SEARCH_TERMS: tuple[str, ...] = tuple(all_search_terms())
