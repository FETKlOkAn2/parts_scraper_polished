# app/worker.py
import os, json, boto3, tempfile, pathlib, traceback
from image_proc.run import process_shard
from obs import get_logger
from obs.metrics import build_emitter


REGION    = os.getenv("AWS_REGION", "us-east-1")
QUEUE_URL = os.getenv("QUEUE_URL")
BUCKET    = os.getenv("BUCKET")

# choose a temp dir that works everywhere (Windows/Mac/Linux)
LOCAL_TMP_DIR = os.getenv("LOCAL_TMP_DIR", tempfile.gettempdir())
pathlib.Path(LOCAL_TMP_DIR).mkdir(parents=True, exist_ok=True)


sqs = boto3.client("sqs", region_name=REGION)
s3  = boto3.client("s3",  region_name=REGION)

log = get_logger("image_proc.worker")
metrics = build_emitter(stage="image_proc")


def output_exists(basename: str) -> bool:
    try:
        s3.head_object(Bucket=BUCKET, Key=f"proc_jobs/{basename}.done")
        return True
    except s3.exceptions.ClientError:
        return False


def mark_done(basename: str):
    s3.put_object(Bucket=BUCKET, Key=f"proc_jobs/{basename}.done", Body=b"ok")


def handle_message(m):
    body = json.loads(m["Body"])
    key  = body["s3_key"]
    basename = os.path.basename(key)
    local_in = os.path.join(LOCAL_TMP_DIR, basename)

    bound = log.bind(shard=basename, s3_key=key)

    if output_exists(basename):
        bound.info("shard already complete, skipping")
        metrics.count("ShardsSkipped")
        return

    bound.info("shard download starting", local_path=local_in)
    s3.download_file(BUCKET, key, local_in)

    bound.info("shard processing")
    with metrics.timer("Shard", shard=basename):
        process_shard(local_in)
    mark_done(basename)
    bound.info("shard complete")


def main():
    log.info(
        "worker starting",
        region=REGION,
        queue=QUEUE_URL,
        bucket=BUCKET,
    )

    resp = sqs.receive_message(
        QueueUrl=QUEUE_URL,
        MaxNumberOfMessages=1,
        WaitTimeSeconds=20,
        VisibilityTimeout=4000,
        AttributeNames=["ApproximateReceiveCount"],
    )
    msgs = resp.get("Messages", [])
    if not msgs:
        log.info("no work; exiting")
        metrics.flush()
        return 0

    m = msgs[0]
    tries = int(m.get("Attributes", {}).get("ApproximateReceiveCount", "1"))

    try:
        handle_message(m)
        sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=m["ReceiptHandle"])
        log.info("message processed & deleted; exiting one-and-done", tries=tries)
        return 0
    except Exception as e:
        log.exception("error processing message", tries=tries, error=str(e))
        traceback.print_exc()

        try:
            sqs.change_message_visibility(
                QueueUrl=QUEUE_URL,
                ReceiptHandle=m["ReceiptHandle"],
                VisibilityTimeout=60 if tries < 3 else 0,
            )
        except Exception as e2:
            log.warning("change_message_visibility failed", error=str(e2))
        return 2
    finally:
        metrics.flush()


if __name__ == "__main__":
    main()
