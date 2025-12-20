from app.mcp.registry import mcp
# agent.py ထဲက Deep Brain logic ကို လှမ်းခေါ်မယ်
from app.brain.agent import ask_jarvis 

@mcp.tool(category="reasoning")
async def consult_deep_brain(query: str):
    """
    Uses the advanced Gemini 2.5 Flash model for complex reasoning, 
    coding, factual queries, or detailed explanations.
    Use this tool when the user asks something that requires deep thinking.
    
    Args:
        query: The user's question or request.
    """
    try:
        print(f"[Fast Brain] 🔄 Handoff to Deep Brain: {query}")
        # ask_jarvis က Gemini 2.5 Flash ကို သုံးထားပြီးသားပါ
        response = await ask_jarvis(query)
        return response
    except Exception as e:
        return f"Cognitive Error: {e}"