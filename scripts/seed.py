
"""Seed demo users and optionally generate fake leads.

Usage:
    python -m scripts.seed --leads 0       # Create missing demo users only
    python -m scripts.seed --leads 10000   # Create missing users and 10,000 fake leads
"""

import argparse
import random
from datetime import datetime, timedelta, timezone

from faker import Faker
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.enums import Role
from app.models import Lead, User
from app.security import hash_password

SOURCES = ["website", "referral", "linkedin", "cold_call", "event", "ads"]
STATUSES = ["new", "contacted", "won", "lost"]
STATUS_WEIGHTS = [45, 30, 10, 15]

DEMO_USERS = [
    ("admin@leadflow.com", "Admin User", Role.ADMIN, "Admin@12345"),
    ("agent1@leadflow.com", "Agent One", Role.AGENT, "Agent@12345"),
    ("agent2@leadflow.com", "Agent Two", Role.AGENT, "Agent@12345"),
    ("agent3@leadflow.com", "Agent Three", Role.AGENT, "Agent@12345"),
]


def seed_users(db) -> None:
    """Create missing demo users without changing existing users or passwords."""
    for email, name, role, password in DEMO_USERS:
        normalized_email = email.lower()

        existing_user = db.scalar(
            select(User).where(User.email == normalized_email)
        )

        if existing_user is not None:
            print(f"User already exists: {normalized_email}", flush=True)
            continue

        user = User(
            email=normalized_email,
            full_name=name,
            role=role.value,
            hashed_password=hash_password(password),
        )
        db.add(user)

        # Flush each new user so its unique email is checked immediately.
        try:
            db.flush()
            print(f"Created demo user: {normalized_email}", flush=True)
        except IntegrityError:
            db.rollback()
            # Another process may have created this email concurrently.
            existing_user = db.scalar(
                select(User).where(User.email == normalized_email)
            )
            if existing_user is None:
                raise
            print(f"User already exists: {normalized_email}", flush=True)

    db.commit()


def main(total_leads: int, batch_size: int = 1000) -> None:
    if total_leads < 0:
        raise ValueError("--leads must be zero or greater")

    fake = Faker()
    Faker.seed(42)
    random.seed(42)

    db = SessionLocal()

    try:
        seed_users(db)

        if total_leads == 0:
            print("User seeding complete. No fake leads requested.", flush=True)
            return

        owner_ids = list(db.scalars(select(User.id)).all())

        if not owner_ids:
            raise RuntimeError("No users found; cannot assign lead owners.")

        now = datetime.now(timezone.utc)
        created = 0

        while created < total_leads:
            count = min(batch_size, total_leads - created)
            rows = []

            for _ in range(count):
                timestamp = now - timedelta(
                    days=random.randint(0, 365),
                    minutes=random.randint(0, 1440),
                )

                rows.append(
                    {
                        "name": fake.name(),
                        "email": fake.email(),
                        "phone": fake.msisdn()[:12],
                        "company": fake.company()[:120],
                        "source": random.choice(SOURCES),
                        "status": random.choices(
                            STATUSES, weights=STATUS_WEIGHTS
                        )[0],
                        "owner_id": random.choice(owner_ids),
                        "created_at": timestamp,
                        "updated_at": timestamp,
                    }
                )

            db.bulk_insert_mappings(Lead, rows)
            db.commit()

            created += count
            print(
                f"Inserted {created}/{total_leads} leads",
                flush=True,
            )

        print("Lead seeding complete.", flush=True)

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--leads", type=int, default=10000)
    args = parser.parse_args()
    main(args.leads)
