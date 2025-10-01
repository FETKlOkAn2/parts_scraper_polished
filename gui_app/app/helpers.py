import io
from math import ceil
import boto3
import json
from dotenv import load_dotenv
load_dotenv()

class Helper:
    def __init__(self, db):
        self.db = db
        self.sqs = boto3.client("sqs", region_name='us-east-1')
        self.ec2 = boto3.client("ec2")


    def split_data_and_upload_jobs(self,df, bucket, prefix, chunk_size):
        n = len(df)
        num_chunks = ceil(n /chunk_size) if n else 0
        if num_chunks ==0:
            print("Dataframe is empty, nothing to upload.")
            return
        
        base_prefix = prefix.rstrip('/')
        
        for i in range(num_chunks):
            start = i * chunk_size
            stop = min(start + chunk_size, n)
            chunk = df.iloc[start:stop]

            csv_buf = io.StringIO()
            chunk.to_csv(csv_buf, index=False, header=True)
            data_bytes = csv_buf.getvalue().encode("utf-8")

            chunk_key = f"{base_prefix}/chunk_{i+1}.csv"

            self.db.s3.put_object(
                Body=data_bytes,
                Bucket=bucket,
                Key=chunk_key,
                ContentType='text/csv'
            )

        return num_chunks
    
    def send_chunk_messages(self, job_id: str, queue_url: str, num_chunks: int, key: str):
        """
        Send SQS messages for each chunk file.

        :param job_id: Unique job ID (e.g., "dazetest-run-001")
        :param queue_url: SQS queue URL
        :param num_chunks: Number of chunk files to send
        :param prefix: S3 key prefix (default "jobs")
        """
        for i in range(1, num_chunks + 1):
            s3_key = f"{key}/chunk_{i}.csv"
            message_body = {
                "job_id": job_id,
                "s3_key": s3_key
            }

            print(f"Sending message for {s3_key}")
            self.sqs.send_message(
                QueueUrl=queue_url,
                MessageBody=json.dumps(message_body)  # must be a string
            )



    def determine_instance_state(self):
        """
        Iterate through all EC2 instances and checks if they are all shutdown yet
        returns state as well to show on GUI.
        """

        paginator = self.ec2.get_paginator("describe_instances")
        kwargs = {}
        kwargs["Filters"] = [{
            "Name": "instance-state-name",
            "Values": ["pending", "running", "stopping", "stopped", "shutting-down", "terminated"]
        }]

        for page in paginator.paginate(**kwargs):
            for res in page.get("Reservations", []):
                for inst in res.get("Instances", []):
                    iid = inst["InstanceId"]
                    state = inst["State"]["Name"]   # <- this is the plain string
                    if state not in ['terminated', 'shutting-down']:
                        return False,state
        return True, 'Terminated'

