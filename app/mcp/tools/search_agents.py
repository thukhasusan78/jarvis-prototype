import os
import httpx
import asyncio
import wikipedia
from ddgs import DDGS
from app.mcp.registry import mcp

# --- CONFIGURATION ---
TAVILY_URL = "https://api.tavily.com/search"
SERPER_URL = "https://google.serper.dev/search"
BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"

# ==========================================
# ✂️ SMART TRUNCATION HELPER
# ==========================================
def smart_truncate(text: str, limit: int) -> str:
    """
    Cuts text to limit but keeps it clean.
    Prevents JSON payload explosion.
    """
    if not text: 
        return ""
    if len(text) <= limit: 
        return text
    return text[:limit] + "...(more)"

# ==========================================
# 🕵️ HELPER FUNCTIONS (API CALLERS)
# ==========================================

async def _fetch_tavily(query: str):
    """
    Fetches Market/News data.
    - PRIORITIZES: The 'Answer' (AI Summary).
    - LIMITS: Top 5 Results, 500 chars each.
    """
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key: return "Tavily API Key missing."
    
    payload = {
        "api_key": api_key, 
        "query": query,
        "search_depth": "advanced", 
        "max_results": 5,           # <--- 🔥 LIMIT SET TO 5
        "include_answer": True      # <--- Important!
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(TAVILY_URL, json=payload, timeout=15.0)
            data = resp.json()
            
            # 1. AI Summary (Keep up to 3000 chars as requested)
            summary = smart_truncate(data.get("answer", "No summary available."), 3000)
            
            # 2. Sources (Now includes URL)
            results = data.get("results", [])
            sources = "\n".join([
                # 🔥 ADDED: [Source: URL] so Brain can make hyperlinks
                f"- {r['title']}: {smart_truncate(r['content'], 500)} [Source: {r.get('url', '#')}]" 
                for r in results[:5] 
            ])
            
            return f"🤖 [TAVILY INTELLIGENCE]:\nSummary: {summary}\n\nTop Sources:\n{sources}"
            
    except Exception as e:
        return f"Tavily Error: {str(e)[:100]}"

async def _fetch_serper(query: str):
    """
    Fetches Google Data.
    - LIMITS: Top 5 Results, 300 chars snippet each.
    """
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key: return "Serper API Key missing."

    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
    payload = {
        "q": query, 
        "num": 5  # <--- 🔥 LIMIT SET TO 5
    } 
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(SERPER_URL, headers=headers, json=payload, timeout=10.0)
            data = resp.json()
            organic = data.get("organic", [])
            
            # Extract Snippets + Links
            snippets = "\n".join([
                # 🔥 ADDED: [Source: URL]
                f"- {r['title']} ({r.get('date', '')}): {smart_truncate(r.get('snippet', ''), 300)} [Source: {r.get('link', '#')}]" 
                for r in organic
            ])
            return f"🔍 [GOOGLE/SERPER DATA]:\n{snippets}"
            
    except Exception as e:
        return f"Serper Error: {str(e)[:100]}"

async def _fetch_brave(query: str):
    """
    Fetches Breaking News.
    - LIMITS: Top 5 Results.
    """
    api_key = os.getenv("BRAVE_API_KEY")
    if not api_key: return "Brave API Key missing."

    headers = {"X-Subscription-Token": api_key, "Accept": "application/json"}
    
    try:
        async with httpx.AsyncClient() as client:
            # freshness=pd (Past Day) ensures latest news
            resp = await client.get(f"{BRAVE_URL}?q={query}&freshness=pd&count=5", headers=headers, timeout=10.0)
            data = resp.json()
            
            web_results = data.get("web", {}).get("results", [])
            
            # Breaking news + URL
            news_items = "\n".join([
                # 🔥 ADDED: [Source: URL]
                f"- {r['title']} ({r.get('age', 'Just now')}): {smart_truncate(r.get('description', ''), 300)} [Source: {r.get('url', '#')}]" 
                for r in web_results
            ])
            return f"⚡ [BRAVE BREAKING NEWS]:\n{news_items}"
            
    except Exception as e:
        return f"Brave Error: {str(e)[:100]}"

# ==========================================
# 🛠️ AGENT TOOLS (EXPOSED TO JARVIS)
# ==========================================

@mcp.tool(category="research")
async def consult_knowledge_agent(topic: str):
    """
    AGENT 1: WIKIPEDIA
    Use for: Biographies, History, Static Facts.
    """
    try:
        summary = wikipedia.summary(topic, sentences=4)
        # Wikipedia page URL is auto-generated usually, but summary is enough here.
        # If needed: page = wikipedia.page(topic); page.url
        return f"📚 [KNOWLEDGE BASE (WIKI)]:\n{summary}"
    except Exception as e:
        return f"Wiki Error: {str(e)[:100]}"

@mcp.tool(category="research")
async def consult_breaking_news(query: str):
    """
    AGENT 2: BRAVE SEARCH
    Use for: Real-time events, Breaking news (last 24h).
    """
    return await _fetch_brave(query)

@mcp.tool(category="research")
async def perform_deep_market_research(topic: str):
    """
    AGENT 3: FUSION AGENT (TAVILY + SERPER)
    Use for: Market analysis, Product research, Trends.
    Executes in PARALLEL.
    """
    print(f"🚀 DEBUG: Launching Parallel Agents for '{topic}'...")
    
    # Run both simultaneously
    tavily_task = _fetch_tavily(topic)
    serper_task = _fetch_serper(topic)
    
    results = await asyncio.gather(tavily_task, serper_task)
    tavily_data, serper_data = results
    
    return f"""
🌟 FUSION REPORT FOR: '{topic}'
=================================================
{tavily_data}

{serper_data}
=================================================
"""

@mcp.tool(category="research")
async def consult_fallback_search(query: str):
    """
    AGENT 4: FALLBACK (DuckDuckGo)
    """
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
            # 🔥 ADDED: [Source: URL]
            formatted = "\n".join([f"- {r['title']}: {smart_truncate(r['body'], 200)} [Source: {r.get('href', '#')}]" for r in results])
            return f"🦆 [FALLBACK SEARCH]:\n{formatted}"
    except Exception as e:
        return f"DDG Error: {str(e)[:100]}"