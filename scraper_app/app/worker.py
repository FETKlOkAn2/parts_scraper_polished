# app/worker.py
import os, time, json, boto3, tempfile, pathlib
from scraper.run import process_shard


REGION        = os.getenv("AWS_REGION")
QUEUE_URL     = os.getenv("QUEUE_URL")
INPUT_BUCKET  = os.getenv("BUCKET")

# choose a temp dir that works everywhere (Windows/Mac/Linux)
LOCAL_TMP_DIR = os.getenv("LOCAL_TMP_DIR", tempfile.gettempdir())
pathlib.Path(LOCAL_TMP_DIR).mkdir(parents=True, exist_ok=True)


sqs = boto3.client("sqs", region_name=REGION)
s3  = boto3.client("s3",  region_name=REGION)

def handle_message(m):
    body = json.loads(m["Body"])
    key  = body["s3_key"]              # e.g., jobs/chunk_1.csv

    basename  = os.path.basename(key)                 # chunk_1.csv
    local_in  = f"/tmp/{basename}"    # still write temp as .results.json

    print(f"[worker] downloading s3://{INPUT_BUCKET}/{key} -> {local_in}")
    s3.download_file(INPUT_BUCKET, key, local_in)

    print(f"[worker] processing shard {local_in}")
    process_shard(local_in)

def main():
    empty_polls = 0
    max_empty_polls_before_exit = 5

    print(f"[worker] starting in {REGION}")
    print(f"[worker] queue={QUEUE_URL}")
    print(f"[worker] input_bucket={INPUT_BUCKET}")

    while True:
        resp = sqs.receive_message(
            QueueUrl=QUEUE_URL,
            MaxNumberOfMessages=5,
            WaitTimeSeconds=20,
            VisibilityTimeout=900
        )
        msgs = resp.get("Messages", [])
        if not msgs:
            empty_polls += 1
            print(f"[worker] queue empty ({empty_polls}/{max_empty_polls_before_exit})")
            if empty_polls >= max_empty_polls_before_exit:
                print("[worker] exiting: queue appears drained")
                break
            continue

        empty_polls = 0
        for m in msgs:
            try:
                handle_message(m)
                sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=m["ReceiptHandle"])
                print("[worker] message processed & deleted")
            except Exception as e:
                print(f"[worker] ERROR processing message: {e}")

if __name__ == "__main__":
    main()
