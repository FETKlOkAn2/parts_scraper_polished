# runner.py
import json, time, os, urllib.parse
from openai import OpenAI


class AIWatermark:
  def __init__(self):
    self.client = OpenAI()

    self.POLL_EVERY_SEC = 30
    self.BACKOFF_MAX = 300  # cap backoff at 5 min

  def basename(self,url):
      return os.path.basename(urllib.parse.urlparse(url).path)

  def make_lines(self, urls):
      for u in urls:
          name = self.basename(u)
          yield {
            "custom_id": name,
            "method": "POST",
            "url": "/v1/responses",
            "body": {
              "model": "gpt-4o-mini",
              "input": [{
                "role": "user",
                "content": [
                  {"type":"input_text","text":
                  "Return ONLY JSON for this schema. Detect overlaid watermarks/"
                  "logos/brand text/patterns that are NOT part of the product label. "
                  "If unsure, use false."},
                  {"type":"input_image","image_url": u}
                ]
              }],
              "response_format": {
                "type": "json_schema",
                "json_schema": {
                  "name": "watermark_result",
                  "strict": True,
                  "schema": {
                    "type": "object",
                    "properties": {"watermark": {"type":"boolean"}},
                    "required": ["watermark"],
                    "additionalProperties": False
                  }
                }
              },
              "temperature": 0
            }
          }

  def submit_batch(self, lines, path):
      with open(path, "w", encoding="utf-8") as f:
          for line in lines:
              f.write(json.dumps(line) + "\n")
      up = self.client.files.create(file=open(path,"rb"), purpose="batch")   # upload JSONL
      b = self.client.batches.create(input_file_id=up.id, endpoint="/v1/responses",
                                completion_window="24h")
      return b.id

  def poll_until_done(self, batch_id):
      backoff = self.POLL_EVERY_SEC
      while True:
          b = self.client.batches.retrieve(batch_id)
          if b.status in ("completed","failed","expired","cancelling","cancelled"):
              return b
          time.sleep(backoff)
          backoff = min(int(backoff * 1.5), self.BACKOFF_MAX)

  def download_output(self, file_id, to_path):
      out = self.client.files.content(file_id).text
      with open(to_path, "w", encoding="utf-8") as f:
          f.write(out)

  def parse_output(self, jsonl_path):
      m = {}
      with open(jsonl_path, "r", encoding="utf-8") as f:
          for line in f:
              if not line.strip(): continue
              obj = json.loads(line)
              name = obj["custom_id"]
              content = obj["response"]["output"][0]["content"][0]
              wm = content.get("json", json.loads(content["text"]))["watermark"]
              m[name] = bool(wm)
      return m

# ---------- orchestrate ----------
# Load your 60k image URLs (e.g., from S3 manifest)

  def main(self):

    all_urls = [line.strip() for line in open("urls.txt") if line.strip()]

    CHUNK = 10_000
    batch_ids = []
    for i in range(0, len(all_urls), CHUNK):
        chunk = all_urls[i:i+CHUNK]
    #     bid = self.submit_batch(self.make_lines(chunk), f"batch_{i//CHUNK}.jsonl")
    #     print("submitted:", bid, f"({len(chunk)} requests)")
    #     batch_ids.append((bid, i//CHUNK))

    # # Poll and collect outputs
    # final_map = {}
    # for bid, idx in batch_ids:
    #     b = self.poll_until_done(bid)
    #     print("finished:", bid, b.status)
    #     if b.status == "completed":
    #         out_path = f"batch_{idx}_output.jsonl"
    #         self.download_output(b.output_file_id, out_path)
    #         final_map.update(self.parse_output(out_path))

    # # One big JSON
    # with open("watermarks.json", "w", encoding="utf-8") as f:
    #     json.dump(final_map, f, indent=2)
    # print("Wrote watermarks.json")

if __name__ == "__main__":
    watermark = AIWatermark()
    watermark.main()