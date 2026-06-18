"""
Initialize the MySQL schema for Railway or any MySQL-compatible database.

The schema file contains MySQL client directives such as DELIMITER and USE.
This script executes it through mysql-connector-python so it can run in a
Railway deploy container without requiring the mysql CLI.
"""

from pathlib import Path
import re
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.config import get_config


def strip_database_directives(sql: str) -> str:
    sql = re.sub(
        r"CREATE\s+DATABASE\s+IF\s+NOT\s+EXISTS\s+\w+\s+CHARACTER\s+SET\s+\w+\s+COLLATE\s+[\w_]+;",
        "",
        sql,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    sql = re.sub(r"^\s*USE\s+\w+\s*;\s*$", "", sql, flags=re.IGNORECASE | re.MULTILINE)
    return sql


def split_mysql_statements(sql: str):
    delimiter = ";"
    statement_lines = []

    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped:
            statement_lines.append(line)
            continue

        if stripped.upper().startswith("DELIMITER "):
            delimiter = stripped.split(maxsplit=1)[1]
            continue

        statement_lines.append(line)
        current = "\n".join(statement_lines).strip()
        if current.endswith(delimiter):
            yield current[: -len(delimiter)].strip()
            statement_lines = []

    trailing = "\n".join(statement_lines).strip()
    if trailing:
        yield trailing


def main() -> int:
    try:
        import mysql.connector
    except ImportError:
        print("mysql-connector-python is required. Run: pip install -r requirements.txt")
        return 1

    config = get_config()
    schema_path = PROJECT_ROOT / "scripts" / "001_create_database_schema.sql"
    schema_sql = strip_database_directives(schema_path.read_text(encoding="utf-8"))
    statements = [stmt for stmt in split_mysql_statements(schema_sql) if stmt]

    print(
        f"Connecting to MySQL at {config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME} "
        f"as {config.DB_USER}"
    )

    connection = mysql.connector.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.DB_NAME,
        connection_timeout=config.DB_CONNECTION_TIMEOUT,
    )

    try:
        cursor = connection.cursor()
        for index, statement in enumerate(statements, start=1):
            cursor.execute(statement)
            while cursor.nextset():
                pass
            print(f"Executed schema statement {index}/{len(statements)}")

        connection.commit()
        print("Database schema initialized successfully.")
        return 0

    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
