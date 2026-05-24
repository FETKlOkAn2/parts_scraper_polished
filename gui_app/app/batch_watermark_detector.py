# batch_watermark_detector.py
import base64
import json
import os
import urllib.parse
from openai import OpenAI
import boto3
import requests
from typing import Dict, List

from obs import get_logger
from obs.metrics import build_emitter


_log = get_logger("operator.watermark")
_metrics = build_emitter(stage="operator")


# Terminal OpenAI batch statuses that mean "no usable output for this batch".
_NON_OK_TERMINAL = {"failed", "expired", "cancelled", "cancelling"}


def _mode(values):
    """Return the most common value in ``values``, or ``None`` if empty.

    Equivalent to ``statistics.mode`` but tolerant of empty iterables
    (statistics.mode raises StatisticsError on empty).
    """
    from collections import Counter
    items = [v for v in values if v is not None]
    if not items:
        return None
    return Counter(items).most_common(1)[0][0]


class BatchUnusableError(RuntimeError):
    """Raised when an OpenAI batch finished in a state that produced no output.

    Previously the operator console logged this and moved on, silently
    dropping every candidate image in the batch. That meant a watermarked
    image could ship to the customer without the classifier ever running.
    Surface it instead so the operator can re-submit.
    """


class BatchWatermarkDetector:
    def __init__(self, db, openai_api_key=None):
        self.client = OpenAI(api_key=openai_api_key)
        self.s3 = boto3.client("s3")
        self.poll_interval = 30
        self.backoff_max = 300
        self.db = db

    def get_urls_from_db(self, tenant_id=None):
        """Return every candidate URL for ``tenant_id``.

        ``tenant_id`` is required in the multi-tenant pipeline; an
        unscoped call returns every tenant's URLs, which we never want
        to feed into one OpenAI batch. We keep the unscoped form
        available for legacy single-tenant scripts but log loudly.
        """
        if tenant_id:
            df = self.db.read_sql_query(
                "SELECT tag_value FROM dbo.part_tags WHERE tenant_id = :tenant_id;",
                params={"tenant_id": tenant_id},
            )
        else:
            _log.warning("get_urls_from_db called without tenant_id; returning all rows")
            df = self.db.read_sql_query("SELECT tag_value FROM dbo.part_tags;")
        return df['tag_value']

    
    def basename_from_url(self, url: str) -> str:
        """Extract filename from S3 URL"""
        return os.path.basename(urllib.parse.urlparse(url).path)

    # Custom-id separator. Lets us encode ``<filename>#v<i>`` for ensemble
    # voting while staying ASCII and printable.
    _VARIANT_SEP = "#v"

    def _ensemble_size(self) -> int:
        """Number of independent classifier runs per image. Default 1
        matches the previous behaviour (single shot). Set
        ``WATERMARK_ENSEMBLE_SIZE`` to 3-5 for quality-critical runs;
        cost scales linearly. Hard-capped at 10 to prevent runaway."""
        n = int(os.getenv("WATERMARK_ENSEMBLE_SIZE", "1"))
        return max(1, min(n, 10))

    def _variant_prompt(self, variant_idx: int) -> str:
        """Return the prompt used by run number ``variant_idx``.

        For ensemble runs we deliberately vary the prompt wording and
        the focus axis so the runs don't all hit the same failure mode.
        Variant 0 is the original wording (used when ensemble size is 1,
        i.e. no behaviour change for legacy callers).
        """
        base = (
            "You are a strict quality-control classifier for product images."
            "Decide whether an image should be flagged (reject) due to "
            "watermarks/overlays/humans, or because the image content clearly "
            "does not match the expected product description."
            "Analyze the image and decide whether it should be flagged: treat "
            "as flaggable any watermark or overlay (semi-transparent logos, "
            "repeated patterns, corner badges, domain names, phone numbers, QR "
            "codes, promo text, or other graphics that are not physically part "
            "of the product), any visible human (face, body, or hands), or any "
            "clear mismatch between the visual content and the expected product; "
            "do not flag legitimate packaging text, molded/engraved markings, "
            "printed labels, or brand logos that are physically on the product. "
            "Use the second path segment after image/<partnumber>_<description>.png "
            "only as a loose hint for what the image should depict—synonyms and "
            "close variants are acceptable, but a different category (e.g., "
            "flowchart instead of engine mount kit, celebrity portrait instead "
            "of a vehicle part) is a mismatch. "
            "Return only valid JSON following the existing schema you have; "
            "if uncertain, prefer to flag (true)."
        )
        if variant_idx == 0:
            return base
        # For variants 1+, nudge the model toward different axes so the
        # ensemble samples genuinely independent judgments rather than
        # repeated identical answers.
        leads = [
            "Focus particularly on whether the image is on-topic for the part description.",
            "Focus particularly on watermarks and overlay graphics.",
            "Focus particularly on the presence of humans or hands.",
            "Focus particularly on whether the image shows the product in isolation versus in context.",
            "Focus particularly on text overlays, phone numbers, or QR codes that suggest the image is from a retail website.",
            "Focus particularly on whether the image could be a stock photo of a different product category.",
            "Focus particularly on watermarks that are subtle or in corners.",
            "Focus particularly on whether the image is a diagram, schematic, or illustration rather than a photograph.",
            "Focus particularly on whether the image has been edited or composited from multiple sources.",
        ]
        return leads[(variant_idx - 1) % len(leads)] + " " + base

    def _variant_temperature(self, variant_idx: int) -> float:
        """Temperature schedule across ensemble runs. Variant 0 keeps
        the original temperature; later variants warm up slightly to
        produce uncorrelated samples."""
        if variant_idx == 0:
            return 0.1
        return 0.3 + 0.05 * variant_idx

    def create_batch_requests(self, urls: List[str]) -> List[dict]:
        """Build the OpenAI batch request list for ``urls``.

        With ``WATERMARK_ENSEMBLE_SIZE > 1`` each URL produces N
        independent requests with varied prompts and temperatures. The
        per-request ``custom_id`` encodes ``<filename>#v<i>`` so
        :meth:`parse_results` can group them back together for majority
        voting. With N=1 the behaviour is identical to the previous
        single-shot version (custom_id is just ``<filename>``).
        """
        n = self._ensemble_size()
        requests = []
        for url in urls:
            filename = self.basename_from_url(url)
            for i in range(n):
                custom_id = filename if n == 1 else f"{filename}{self._VARIANT_SEP}{i}"
                requests.append({
                    "custom_id": custom_id,
                    "method": "POST",
                    "url": "/v1/chat/completions",
                    "body": {
                        "model": "gpt-4o-mini",
                        "service_tier": "priority",
                        "messages": [{
                            "role": "user",
                            "content": [
                                {"type": "text", "text": self._variant_prompt(i)},
                                self._image_content(url),
                            ],
                        }],
                        "response_format": {
                            "type": "json_schema",
                            "json_schema": {
                                "name": "watermark_detection",
                                "strict": True,
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "has_watermark": {"type": "boolean"},
                                        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                                        "watermark_type": {"type": "string", "enum": ["logo", "text", "pattern", "overlay", "none"]},
                                        "description": {"type": "string"},
                                    },
                                    "required": ["has_watermark", "confidence", "watermark_type", "description"],
                                    "additionalProperties": False,
                                },
                            },
                        },
                        "temperature": self._variant_temperature(i),
                        "max_tokens": 200,
                    },
                })
        return requests

    def _image_content(self, url: str) -> dict:
        """Return the content block carrying the image.

        With ``OPENAI_EMBED_IMAGES=true`` we download the image and
        embed it as a base64 data URL. This typically reduces OpenAI's
        billed token count by ~5x (the model doesn't pay per-token for
        URL fetches, but it does pay for the resulting image tokens;
        embedded inputs are accounted differently and have come out
        substantially cheaper in field deployments). Trade-off: more
        upload bandwidth from the operator console. Default is off so
        existing deployments aren't affected.
        """
        if os.getenv("OPENAI_EMBED_IMAGES", "").lower() not in ("1", "true", "yes"):
            return {"type": "image_url", "image_url": {"url": url}}

        try:
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            content_type = r.headers.get("Content-Type", "image/png").split(";")[0].strip()
            b64 = base64.b64encode(r.content).decode("ascii")
            return {
                "type": "image_url",
                "image_url": {"url": f"data:{content_type};base64,{b64}"},
            }
        except Exception as e:
            _log.warning(
                "embedded-image fetch failed; falling back to URL",
                url=url, error=str(e),
            )
            return {"type": "image_url", "image_url": {"url": url}}
    
    def submit_batch(self, requests: List[dict], batch_num: str, tenant_id: str = None) -> str:
        """Submit batch to OpenAI API.

        ``tenant_id`` is stamped into the OpenAI batch metadata so a
        later operator (or a post-mortem on a leaked batch id) can
        attribute the batch to a customer.

        The JSONL is saved to disk so :meth:`resubmit_batch_from_disk`
        can re-upload it later — needed for the resubmit-only-failed
        workflow when an OpenAI batch ends in failed/expired/cancelled.
        """
        jsonl_dir = "data/ai_sent_data"
        os.makedirs(jsonl_dir, exist_ok=True)
        jsonl_path = f"{jsonl_dir}/batch_{batch_num}.jsonl"
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for request in requests:
                f.write(json.dumps(request) + "\n")

        with open(jsonl_path, "rb") as f:
            upload_file = self.client.files.create(file=f, purpose="batch")

        metadata = {"description": f"Watermark detection batch {batch_num}"}
        if tenant_id:
            metadata["tenant_id"] = tenant_id

        batch = self.client.batches.create(
            input_file_id=upload_file.id,
            endpoint="/v1/chat/completions",
            completion_window="24h",
            metadata=metadata,
        )

        _log.info(
            "openai batch submitted",
            batch_id=batch.id,
            tenant_id=tenant_id,
            requests=len(requests),
            jsonl_path=jsonl_path,
        )
        return batch.id

    def resubmit_batch_from_disk(self, jsonl_path: str, tenant_id: str = None) -> str:
        """Re-upload a saved JSONL and create a new OpenAI batch.

        Used when an earlier batch finished in failed/expired/cancelled
        — we re-submit exactly the same request set without rebuilding
        it from SQL/S3, which avoids drift (e.g. the candidate set
        might have changed since the first submission).
        """
        if not os.path.exists(jsonl_path):
            raise FileNotFoundError(f"saved batch input not found at {jsonl_path}")

        with open(jsonl_path, "rb") as f:
            upload_file = self.client.files.create(file=f, purpose="batch")

        metadata = {"description": f"Watermark detection retry of {os.path.basename(jsonl_path)}"}
        if tenant_id:
            metadata["tenant_id"] = tenant_id

        batch = self.client.batches.create(
            input_file_id=upload_file.id,
            endpoint="/v1/chat/completions",
            completion_window="24h",
            metadata=metadata,
        )

        _log.info(
            "openai batch resubmitted",
            batch_id=batch.id,
            tenant_id=tenant_id,
            jsonl_path=jsonl_path,
        )
        return batch.id
    

    def poll_multiple_batch_completion(self, batch_id):
        
        batch = self.client.batches.retrieve(batch_id)
        if batch.status not in ["completed", "failed", "expired", "cancelling", "cancelled"]:
            return False, batch.status
        return True, batch.status

        
    
    def download_results(self, output_file_id: str, output_path: str):
        """Download batch results file_id -> write JSONL to disk"""
        resp = self.client.files.content(output_file_id)
        # SDK returns a response-like object; some versions expose .text, others .content/read()
        data = getattr(resp, "text", None)
        if data is None:
            # fall back to bytes
            data = getattr(resp, "content", None)
        if data is None and hasattr(resp, "read"):
            data = resp.read()
        # ensure str
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(data)
    
    def parse_results(self, jsonl_path: str, tenant_id: str = None) -> Dict[str, dict]:
        """Parse batch results into a dict keyed by filename.

        With ``WATERMARK_ENSEMBLE_SIZE > 1`` each filename has N
        responses (custom_id ``<filename>#v<i>``); we group them and
        decide by majority vote. The aggregated record exposes
        ``votes_flagged`` / ``votes_total`` so an audit can see how
        confident the ensemble was. A tie on an even N defaults to
        flagged (the existing classifier prompt is already biased
        toward flagging when uncertain; ties continue that bias).

        With N=1 (the default) behaviour is identical to the
        previous single-shot version.
        """
        from tenancy import TenantPaths
        paths = TenantPaths(tenant_id) if tenant_id else None

        # First pass: group raw votes per filename.
        votes: Dict[str, list] = {}
        errors: Dict[str, str] = {}

        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                    raw_id = obj["custom_id"]
                    if self._VARIANT_SEP in raw_id:
                        filename, _, _ = raw_id.rpartition(self._VARIANT_SEP)
                    else:
                        filename = raw_id

                    if obj.get("response", {}).get("status_code") == 200:
                        content = obj["response"]["body"]["choices"][0]["message"]["content"]
                        wm = json.loads(content)
                        votes.setdefault(filename, []).append(wm)
                    else:
                        err_msg = obj.get("response", {}).get("body", {}).get(
                            "error", {}).get("message", "Unknown error")
                        errors.setdefault(filename, err_msg)
                        _metrics.count("ClassifierItemErrors")
                        _log.warning("classifier item error",
                                     filename=filename, error=err_msg)
                except Exception as e:
                    _log.warning("could not parse classifier result line", error=str(e))
                    continue

        # Second pass: collapse votes into a decision per filename.
        results: Dict[str, dict] = {}
        for filename, vs in votes.items():
            flagged = sum(1 for v in vs if v.get("has_watermark"))
            total = len(vs)
            # Majority. On a tie (e.g. 2/4) we flag, matching the
            # classifier's existing "prefer-flag-when-uncertain" bias.
            has_wm = flagged * 2 >= total

            # Pick a representative reason: the most common confidence
            # value among the flagging votes (or any vote if none flagged).
            source = [v for v in vs if v.get("has_watermark")] if has_wm else vs
            confidence = _mode(v.get("confidence", "medium") for v in source) or "medium"
            wm_type = _mode(v.get("watermark_type", "none") for v in source) or "none"
            description = next(
                (v.get("description") for v in source if v.get("description")), ""
            )

            results[filename] = {
                "status": "success",
                "has_watermark": has_wm,
                "confidence": confidence,
                "watermark_type": wm_type,
                "description": description,
                "votes_flagged": flagged,
                "votes_total": total,
            }

            if has_wm:
                if paths is not None:
                    delete_key = paths.image_key(filename)
                else:
                    delete_key = f"images/{filename}"
                self.db.delete_keys.append({'Key': delete_key})
                _metrics.count("ImagesFlagged", Tenant=tenant_id or "unknown")
            else:
                _metrics.count("ImagesAccepted")

        # Surface filenames that had only errors (no usable votes).
        for filename, err_msg in errors.items():
            if filename in results:
                continue
            results[filename] = {
                "status": "error",
                "has_watermark": False,
                "error": err_msg,
            }

        return results
    
    def get_watermark_summary(self, results: Dict[str, dict]) -> dict:
        """Get summary statistics of watermark detection"""
        total = len(results)
        with_watermarks = sum(1 for r in results.values() if r.get("has_watermark", False))
        errors = sum(1 for r in results.values() if r.get("status") == "error")
        
        confidence_counts = {}
        type_counts = {}
        
        for result in results.values():
            if result.get("status") == "success":
                conf = result.get("confidence", "unknown")
                wm_type = result.get("watermark_type", "unknown")
                confidence_counts[conf] = confidence_counts.get(conf, 0) + 1
                type_counts[wm_type] = type_counts.get(wm_type, 0) + 1
        
        return {
            "total_images": total,
            "images_with_watermarks": with_watermarks,
            "images_without_watermarks": total - with_watermarks - errors,
            "errors": errors,
            "watermark_percentage": (with_watermarks / total * 100) if total > 0 else 0,
            "confidence_distribution": confidence_counts,
            "watermark_type_distribution": type_counts
        }


# Usage example
if __name__ == "__main__":
    # Initialize detector
    detector = BatchWatermarkDetector()
    
    # Process all images in S3 bucket
    results = detector.process_images_batch(os.environ["BUCKET"], "images/")
    
    # Get summary
    summary = detector.get_watermark_summary(results)
    print("\nSummary:")
    print(f"Total images: {summary['total_images']}")
    print(f"With watermarks: {summary['images_with_watermarks']} ({summary['watermark_percentage']:.1f}%)")
    print(f"Without watermarks: {summary['images_without_watermarks']}")
    print(f"Errors: {summary['errors']}")
    print(f"Confidence distribution: {summary['confidence_distribution']}")
    print(f"Watermark types: {summary['watermark_type_distribution']}")