import os
from app.mcp.registry import mcp

# Sandbox Environment
BASE_DIR = os.path.abspath("output")
os.makedirs(BASE_DIR, exist_ok=True)

@mcp.tool(category="fs")
def list_files():
    """Lists all files in the Jarvis output directory."""
    try:
        return os.listdir(BASE_DIR)
    except Exception as e:
        return str(e)

@mcp.tool(category="fs")
def read_file(filename: str):
    """Reads content of a file from the output directory."""
    safe_path = os.path.join(BASE_DIR, os.path.basename(filename))
    if not os.path.exists(safe_path):
        return "File not found."
    
    with open(safe_path, "r", encoding="utf-8") as f:
        return f.read()

@mcp.tool(category="fs")
def write_file(filename: str, content: str):
    """Writes text to a file in the output directory."""
    safe_path = os.path.join(BASE_DIR, os.path.basename(filename))
    with open(safe_path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"File '{filename}' saved successfully."