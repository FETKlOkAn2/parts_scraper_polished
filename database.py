import os
from sqlalchemy import create_engine, text
import pandas as pd
from threading import Lock


class Database:
    def __init__(self):
        self.user = os.getenv("DB_USER")
        self.password = os.getenv("DB_PASSWORD")
        self.host = os.getenv("DB_HOST")
        self.port = os.getenv("DB_PORT", "1433")
        self.db = 'Parts'
        self.driver = "ODBC+Driver+18+for+SQL+Server"
        self.engine = self.get_engine() # Initialize engine in the constructor
        self.lock = Lock() # Thread lock for database access

    def get_engine(self):
        url = (
            f"mssql+pyodbc://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}?driver={self.driver}"
            "&TrustServerCertificate=yes"
        )
        return create_engine(url, pool_pre_ping=True, fast_executemany=True)
    
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

if __name__ == "__main__":
    db = Database()