

def parse_env()-> dict:
    lines = []
    with open("./.env", "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    result = {}

    for line in lines:
        if line == "": continue
        if not "=" in line: continue
        key, val =  line.split("=", maxsplit=2)
        key = key.strip()
        val = val.strip()
        result[key] = val
    
    return result



