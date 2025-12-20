import inspect
import asyncio
import logging
import functools
from typing import Callable, Any, Dict, List

# Logging setup
logger = logging.getLogger("JARVIS_MCP")

class MCPRegistry:
    def __init__(self):
        self._tools: Dict[str, Callable] = {}
        self._schemas: List[Dict] = []

    def tool(self, category: str = "general"):
        """
        Decorator: Function တွေကို MCP Tool အဖြစ် မှတ်ပုံတင်ရန် သုံးသည်။
        Usage: @mcp.tool(category="telegram")
        """
        def decorator(func: Callable):
            # Function နာမည်ကို Category နဲ့တွဲပြီး Unique ဖြစ်အောင်လုပ်မည်
            # e.g., telegram.send_message
            tool_name = f"{category}.{func.__name__}"
            
            # 1. Register Tool
            self._tools[tool_name] = func
            
            # 2. Auto-Generate Schema for Gemini
            schema = self._generate_gemini_schema(func, tool_name)
            self._schemas.append(schema)
            
            logger.info(f"[MCP] 🛠️ Registered Tool: {tool_name}")

            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                return await func(*args, **kwargs)
            return wrapper
        return decorator

    def _generate_gemini_schema(self, func: Callable, name: str) -> Dict:
        """
        Python Function ကိုကြည့်ပြီး Gemini နားလည်မယ့် JSON Schema အလိုလိုထုတ်ပေးခြင်း
        """
        docs = inspect.getdoc(func) or "No description provided."
        sig = inspect.signature(func)
        
        properties = {}
        required_params = []

        for param_name, param in sig.parameters.items():
            if param_name == "self": continue 
            
            # Type Mapping (Python -> JSON)
            type_map = {
                str: "STRING",
                int: "INTEGER",
                float: "NUMBER",
                bool: "BOOLEAN",
                dict: "OBJECT",
                list: "ARRAY"
            }
            # Default to STRING if type not specified
            param_type = type_map.get(param.annotation, "STRING")
            
            properties[param_name] = {
                "type": param_type,
                "description": f"Parameter: {param_name}" 
            }
            
            # Default value မရှိရင် Required လို့ သတ်မှတ်မယ်
            if param.default == inspect.Parameter.empty:
                required_params.append(param_name)

        return {
            "name": name,
            "description": docs,
            "parameters": {
                "type": "OBJECT",
                "properties": properties,
                "required": required_params
            }
        }

    def get_gemini_tools(self):
        """Gemini Setup Message မှာ ထည့်သုံးရမယ့် Tool List"""
        return [{"function_declarations": self._schemas}]

    async def execute(self, name: str, args: Dict[str, Any]):
        """
        Dispatcher: Tool Call လာရင် သက်ဆိုင်ရာ Function ကို ခေါ်ပေးခြင်း
        🔥 LATENCY OPTIMIZATION: 
        Blocking IO (Sync functions) တွေကို Thread ခွဲပြီး Parallel မောင်းပေးသည်။
        """
        if name not in self._tools:
            logger.warning(f"[MCP] ⚠️ Tool not found: {name}")
            return {"error": f"Tool '{name}' not found."}
        
        func = self._tools[name]
        
        try:
            logger.info(f"[MCP] 🚀 Executing: {name} | Args: {args}")
            
            # Check if function is native async (coroutine)
            if inspect.iscoroutinefunction(func):
                result = await func(**args)
            else:
                # 🔥 Critical for Latency: 
                # ရိုးရိုး Python function (Sync) ဆိုရင် Main Loop မပိတ်အောင်
                # သီးသန့် Thread တစ်ခုမှာ Run ပေးသည်။ (Parallel Execution)
                result = await asyncio.to_thread(func, **args)
            
            return {"status": "success", "result": result}

        except Exception as e:
            logger.error(f"[MCP Execution Error] {name}: {e}")
            return {"status": "error", "message": str(e)}

# Global Instance (Singleton)
mcp = MCPRegistry()