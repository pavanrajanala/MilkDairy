import os
import psycopg2
from psycopg2 import pool
from dotenv import load_dotenv


load_dotenv()


DATABASE_URL = os.getenv("DATABASE_URL")


if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is missing in .env"
    )


# =========================================================
# CONNECTION POOL
# =========================================================

connection_pool = psycopg2.pool.ThreadedConnectionPool(
    1,
    5,
    DATABASE_URL
)


# =========================================================
# GET CONNECTION
# =========================================================

def get_db_connection():

    if connection_pool is None:
        raise RuntimeError(
            "Database connection pool is not available."
        )

    return connection_pool.getconn()


# =========================================================
# RELEASE CONNECTION
# =========================================================

def release_db_connection(connection):

    if connection is not None:

        connection_pool.putconn(
            connection
        )