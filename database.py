import os, shutil, stat
import boto3
import re
from botocore.exceptions import NoCredentialsError
from sqlalchemy import create_engine, text
import pandas as pd
from threading import Lock
from typing import Dict, Iterable, List, Iterator, Tuple
from image_processing import Img_Proc


class Database:
    def __init__(self):
        self.user = os.getenv("DB_USER")
        self.password = os.getenv("DB_PASSWORD")
        self.host = os.getenv("DB_HOST")
        self.port = os.getenv("DB_PORT", "1433")
        self.db = 'parts_db'
        self.driver = "ODBC+Driver+18+for+SQL+Server"
        self.engine = self.get_engine() # Initialize engine in the constructor
        self.lock = Lock() # Thread lock for database access
        self.s3 = boto3.client("s3")
        #self.suffix_re = re.compile()
        self.delete_keys = []

    def get_engine(self):
        url = (
            f"mssql+pyodbc://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}?driver={self.driver}"
            "&TrustServerCertificate=yes"
        )
        return create_engine(url, pool_pre_ping=True, fast_executemany=True)
    
    def change_db(self, new_db):
        self.db = new_db

    def execute_sql(self, sql_text):
        with self.lock, self.engine.begin() as conn:
            return conn.execute(text(sql_text))
             
    def read_sql_query(self, sql_text):
        """Execute a SQL query and return the result as a pandas DataFrame."""
        with self.lock, self.engine.begin() as conn:
            return pd.read_sql_query(text(sql_text), conn)
    
    def to_sql(self, df, table_name, if_exists='append', index=False):
        """Write records stored in a DataFrame to a SQL database."""
        with self.lock, self.engine.begin() as conn:
            df.to_sql(table_name, conn, if_exists=if_exists, index=index, method='multi', chunksize=20000)


    def create_table_if_not_exists(self, table_name, df):
        """
        Creates a table if it doesn't exist based on the DataFrame's schema.
        """
        try:
            # Check if the table exists
            table_exists_query = f"IF OBJECT_ID('{table_name}', 'U') IS NOT NULL SELECT 1 ELSE SELECT 0;"
            result = self.read_sql_query(table_exists_query)
            table_exists = result.iloc[0, 0] == 1

            if not table_exists:
                # Build the CREATE TABLE query based on DataFrame's schema
                columns = df.columns
                dtypes = df.dtypes
                sql_dtypes = []
                for col in columns:
                    dtype = dtypes[col]
                    if pd.api.types.is_integer_dtype(dtype):
                        sql_dtype = 'INT'
                    elif pd.api.types.is_float_dtype(dtype):
                        sql_dtype = 'FLOAT'
                    elif dtype == 'datetime64[ns]':
                        sql_dtype = 'DATETIME2'
                    else:
                        sql_dtype = 'NVARCHAR(MAX)'  # Use NVARCHAR(MAX) for TEXT

                    sql_dtypes.append(f'[{col}] {sql_dtype}')

                create_table_query = f"CREATE TABLE [{table_name}] ("
                create_table_query += ', '.join(sql_dtypes)
                create_table_query += ");"

                self.execute_sql(create_table_query)
                print(f"Table {table_name} created successfully.")
            else:
                print(f"Table {table_name} already exists.")
        except Exception as e:
            print(f"Error occurred while creating table {table_name}: {e}")

    def upload_to_folder(self,bucket_name:str, folder_name: str,local_file_path:str, s3_file_name: str=None, delete_after:bool=True):
        s3_file_name = f"{folder_name}/{local_file_path}"
        local_file_path = f"images/images/{local_file_path}"
        try:
            self.s3.upload_file(local_file_path, bucket_name, s3_file_name)
            print(f"uploaded {local_file_path}")
            
            if delete_after:
                os.remove(local_file_path)
                print(f"Deleted local file: {local_file_path}")
        

        except NoCredentialsError:
            print(" AWS credentials not found. Did you run 'aws configure'?\n")
        except Exception as e:
            print(f"Upload failed {e}")

    def download_group(self,bucket: str, group_list:list):
        for key in group_list:
            self.s3.download_file(bucket, f'images/{key}', f'images/images/{key}')



    def empty_dir(self, folder: str) -> None:

        def _on_rm_error(func, path, exc_info):
            # Handle read-only files on Windows
            os.chmod(path, stat.S_IWRITE)
            func(path)

        if not (os.path.isdir(folder) and folder not in ("", "/", "\\")):
            raise ValueError(f"Refusing to operate on suspicious folder: {folder}")
        for entry in os.scandir(folder):
            p = entry.path
            try:
                if entry.is_file() or entry.is_symlink():
                    os.unlink(p)
                else:
                    shutil.rmtree(p, onerror=_on_rm_error)
            except FileNotFoundError:
                pass  # already gone

    def save_data_for_deletion(self, all_data, keep):
        delete = []
        for name in all_data:
            if name not in keep:
                delete.append(name)
        for key in delete:
            self.delete_keys.append({'Key': f'images/{key}'})
        
    def send_delete_request(self):
        deletion_request = {'Objects': self.delete_keys,
                            'Quiet': True}
        self.s3.delete_objects(
            Bucket = 'partsbucket0000',
            Delete= deletion_request
        )

    def retrieve_from_s3(self, bucket:str, prefix:str='', run_img_proc=False) -> Iterator[str]:
        """will have to test after we have 1000 plus and iterates over new page"""

        paginator = self.s3.get_paginator("list_objects_v2")
        previous_control = None
        grouped_strings = []

        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            print('-------------------------------')
            for obj in page.get("Contents", []):
                control_number = obj['Key'].split('_')[-1][0]
                file_name = obj['Key'].split('/')[1]

                if control_number == 'i':
                    continue
                elif previous_control is None:
                    previous_control = control_number
                elif control_number < previous_control:
                    print('\n\t--New Group--')
                    self.download_group(bucket, grouped_strings)

                    if run_img_proc:
                        #hash and compare group - image_processing
                        img_proc = Img_Proc()
                        keep = img_proc.hash_and_compare_group(grouped_strings, method='phash', hash_size=8,
                                distance_thresh=10, testing=True)
                        if not keep:
                            keep = img_proc.hash_and_compare_group(grouped_strings, method='phash', hash_size=8,
                                    distance_thresh=14, testing=True)

                        self.save_data_for_deletion(grouped_strings, keep)
                        self.upload_to_folder('partsbucket0000', 'final', keep[0])
                        self.empty_dir('images/images')

                    previous_control = None
                    grouped_strings = []

                grouped_strings.append(file_name)
                previous_control = control_number



if __name__ == "__main__":
    db = Database()
    db.retrieve_from_s3("partsbucket0000","images", True)
    db.send_delete_request()