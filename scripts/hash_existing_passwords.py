import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import User, app, db
from services.security import hash_password, is_password_hash, verify_password


def main():
    parser = argparse.ArgumentParser(
        description="Convert existing plaintext passwords to Werkzeug hashes."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the password hashes. Without this flag the script is a dry run.",
    )
    parser.add_argument(
        "--backup-confirmed",
        action="store_true",
        help="Confirm that a verified database backup exists.",
    )
    args = parser.parse_args()

    with app.app_context():
        users = User.query.order_by(User.uid).all()
        total = len(users)
        already_hashed = sum(1 for user in users if is_password_hash(user.password))
        pending = total - already_hashed

        print(f"Total users: {total}")
        print(f"Already hashed: {already_hashed}")
        print(f"Plaintext passwords: {pending}")

        if not args.apply:
            print("Dry run only. No passwords were changed.")
            return

        if not args.backup_confirmed:
            raise SystemExit(
                "Refusing to update passwords without --backup-confirmed."
            )

        updated = 0
        try:
            for user in users:
                if is_password_hash(user.password):
                    continue

                original = user.password
                new_hash = hash_password(original)

                if not verify_password(new_hash, original):
                    raise RuntimeError(
                        f"Hash verification failed for user id {user.uid}."
                    )

                user.password = new_hash
                updated += 1

            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        remaining = sum(
            1 for user in User.query.all() if not is_password_hash(user.password)
        )
        print(f"Updated: {updated}")
        print(f"Remaining plaintext passwords: {remaining}")


if __name__ == "__main__":
    main()
