# state_db.py
import json, os, time
from pathlib import Path

class StateDB:
    def __init__(self, path="data/state.json"):
        self.path = Path(path)

    def read(self):
        if not self.path.exists():
            return {}
        with self.path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def write(self, data: dict):
        # stamp last update; atomic replace to avoid partial writes
        data.setdefault("_meta", {})["last_updated_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)  # atomic on Windows & POSIX

    def set(self, **kwargs):
        data = self.read()
        data.update(kwargs)
        self.write(data)
        return data

if __name__ == "__main__":
    state = StateDB()
    
    state.set(image_search_state=True)
    state.set(image_search_state=False)
    state.set(image_watermark_detection=False)
    state.set(image_watermark_detection=False)

    current = state.read()
    currrent_bool = current.get("image_search_state")