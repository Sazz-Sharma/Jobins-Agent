"""
WebSearchTool — Web search with strict timeouts.

Uses the DuckDuckGo search API (free, no API key required) with
socket-level timeouts to prevent hanging on adversarial targets.
"""

from __future__ import annotations

MAX_RESULTS = 5
MAX_OUTPUT_CHARS = 1500
DEFAULT_TIMEOUT = 5


class WebSearchTool:
    """
    Search the web using DuckDuckGo. Returns top results with
    title, snippet, and URL.

    Socket-level timeout of 5 seconds prevents indefinite hangs
    from adversarial or unresponsive endpoints.
    """

    name = "web_search"
    description = (
        "Search the web for information. "
        "Input: a search query string. "
        "Output: top search results with titles, snippets, and URLs. "
        "Use this when you need current information, facts, or data "
        "that you don't already know."
    )

    def __init__(self, timeout: int = DEFAULT_TIMEOUT) -> None:
        self._timeout = timeout

    def run(self, query: str) -> str:
        """Execute a web search and return formatted results."""
        query = query.strip().strip("'\"")
        if not query:
            return "ERROR: No search query provided."

        try:
            from duckduckgo_search import DDGS

            with DDGS(timeout=self._timeout) as ddgs:
                results = list(ddgs.text(query, max_results=MAX_RESULTS))

            if not results:
                return f"No search results found for: {query}"

            output_lines = [f"Search results for: {query}\n"]
            for i, r in enumerate(results, 1):
                title = r.get("title", "No title")
                body = r.get("body", "No snippet")
                href = r.get("href", "No URL")
                output_lines.append(f"{i}. {title}")
                output_lines.append(f"   {body[:200]}")
                output_lines.append(f"   URL: {href}")
                output_lines.append("")

            output = "\n".join(output_lines)

            # Truncate to prevent context flooding
            if len(output) > MAX_OUTPUT_CHARS:
                output = output[:MAX_OUTPUT_CHARS] + "\n... [results truncated]"

            return output

        except ImportError:
            return (
                "ERROR: duckduckgo-search package not installed. "
                "Run: pip install duckduckgo-search"
            )
        except TimeoutError:
            return (
                f"ERROR: Web search timed out after {self._timeout} seconds. "
                "The search endpoint may be unresponsive."
            )
        except ConnectionError as e:
            return f"ERROR: Connection failed during web search: {e}"
        except Exception as e:
            # Never bare except:pass — capture and return the error
            return f"ERROR: Web search failed: {type(e).__name__}: {e}"
