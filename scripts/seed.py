"""Seed demo data: 1 admin, 3 agents and N fake leads.

Usage:
    python -m scripts.seed --leads 10000
"""
import argparse
import random
from datetime import datetime, timedelta, timezone

from faker import Faker
from sqlalchemy import select

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


def main(total_leads: int, batch_size: int = 1000) -> None:
    fake = Faker()
    Faker.seed(42)
    random.seed(42)
    db = SessionLocal()
    try:
        for email, name, role, password in DEMO_USERS:
            if not db.scalar(select(User).where(User.email == email)):
                db.add(User(email=email, full_name=name, role=role.value, hashed_password=hash_password(password)))
        db.commit()
        owner_ids = [u.id for u in db.scalars(select(User)).all()]

        now = datetime.now(timezone.utc)
        created = 0
        while created < total_leads:
            n = min(batch_size, total_leads - created)
            rows = []
            for _ in range(n):
                ts = now - timedelta(days=random.randint(0, 365), minutes=random.randint(0, 1440))
                rows.append(
                    {
                        "name": fake.name(),
                        "email": fake.email(),
                        "phone": fake.msisdn()[:12],
                        "company": fake.company()[:120],
                        "source": random.choice(SOURCES),
                        "status": random.choices(STATUSES, STATUS_WEIGHTS)[0],
                        "owner_id": random.choice(owner_ids),
                        "created_at": ts,
                        "updated_at": ts,
                    }
                )
            db.bulk_insert_mappings(Lead, rows)
            db.commit()
            created += n
            print(f"Inserted {created}/{total_leads} leads", flush=True)
        print("Done. Admin login: admin@leadflow.com / Admin@12345")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--leads", type=int, default=10000)
    args = parser.parse_args()
    main(args.leads)
