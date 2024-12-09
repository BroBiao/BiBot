import json

def read_json_file(file_path):
    with open(file_path, 'r') as f:
        file_text = json.load(f)
    return file_text

def write_to_json_file(json_text, file_path):
    with open(file_path, 'w') as f:
        json.dump(json_text, f)

def timeframe_to_seconds(time_str):
    unit = time_str[-1].lower()
    value = int(time_str[:-1])
    
    if unit == 'm':
        return value * 60
    elif unit == 'h':
        return value * 3600
    else:
        raise ValueError("Unsupported time unit. Please use 'm' for minutes or 'h' for hours.")