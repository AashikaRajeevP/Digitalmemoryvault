import sqlite3
from datetime import date
from pathlib import Path

from sqlalchemy import text

from app import app, db, User, Memory

SQLITE_PATH = Path(__file__).parent / "instance" / "memoryvault.db"


def main():
    with app.app_context():
        if db.engine.url.get_backend_name() != "postgresql":
            raise SystemExit("DATABASE_URL must point to PostgreSQL. Aborting.")

        source = sqlite3.connect(f"file:{SQLITE_PATH.as_posix()}?mode=ro", uri=True)
        source.row_factory = sqlite3.Row

        users = source.execute("SELECT uid, username, password FROM users").fetchall()
        memories = source.execute(
            "SELECT mid, title, message, open_date, created_on, user_id FROM memories"
        ).fetchall()

        for row in users:
            if db.session.get(User, row["uid"]) is None:
                db.session.add(
                    User(uid=row["uid"], username=row["username"], password=row["password"])
                )
        db.session.commit()

        for row in memories:
            if db.session.get(Memory, row["mid"]) is None:
                db.session.add(
                    Memory(
                        mid=row["mid"],
                        title=row["title"],
                        message=row["message"],
                        open_date=date.fromisoformat(row["open_date"]),
                        created_on=date.fromisoformat(row["created_on"]),
                        user_id=row["user_id"],
                    )
                )
        db.session.commit()

        for table, column in (("users", "uid"), ("memories", "mid")):
            db.session.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('{table}', '{column}'), "
                    f"COALESCE((SELECT MAX({column}) FROM {table}), 0) + 1, false)"
                )
            )
        db.session.commit()

        source.close()
        print(f"Copied {len(users)} users and {len(memories)} memories.")


if __name__ == "__main__":
    main()
