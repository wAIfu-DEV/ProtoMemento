import re

def sanitize_for_path(text: str)-> str:
    sanitized = re.sub("[^a-zA-Z0-9_-]", "_", text)

    # handle windows reserved device names
    # thanks chatgpt :)
    reserved_names = {
        "CON", "PRN", "AUX", "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10))
    }
    
    if sanitized.upper() in reserved_names:
        sanitized = f"{sanitized}_safe"
    
    sanitized = sanitized[:255]
    return sanitized
