# Import all tools to register them
from app.mcp.tools import telegram
from app.mcp.tools import location
# from app.mcp.tools import filesystem (ဖျက်ထားသည်)
from app.mcp.tools import reasoning # 🔥 New Tool Added
from app.mcp.tools import search_agents

from app.mcp.registry import mcp

# For external usage
__all__ = ["mcp"]