import os

import psycopg2
from psycopg2 import pool

from dotenv import load_dotenv


load_dotenv()


DATABASE_URL = os.getenv("DATABASE_URL")


if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set in .env"
    )


connection_pool = psycopg2.pool.ThreadedConnectionPool(
    1,
    5,
    DATABASE_URL,
    sslmode="require"
)


def get_db_connection():
    return connection_pool.getconn()


def release_db_connection(connection):
    connection_pool.putconn(connection)