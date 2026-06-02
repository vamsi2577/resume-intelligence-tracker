import asyncio
import random
from datetime import date, timedelta
from faker import Faker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.core.config import settings
from src.models.application import JobApplication, ApplicationStatusHistory

fake = Faker()

STATUSES = ["applied", "screening", "interview", "assessment", "offer", "rejected", "ghosted", "withdrawn"]
SOURCES = ["manual", "resume_generator"]
WORK_TYPES = ["remote", "hybrid", "onsite"]

async def seed_database() -> None:
    print(f"Connecting to database at {settings.DATABASE_URL}...")
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with async_session() as session:
        # First, attempt to clear existing data cleanly
        # Because of cascade deletes, clearing applications should clear history
        # (Assuming you want a clean DB for the E2E test runs)
        try:
            print("Wiping existing job_applications...")
            # Note: A proper truncate might be better for an E2E reset, but this is a simple delete.
            # In PostgreSQL, DELETE FROM job_applications will cascade to history if FK cascade is set.
            await session.execute(JobApplication.__table__.delete())
            await session.commit()
        except Exception as e:
            print(f"Could not clear DB: {e}")
            await session.rollback()

        print("Seeding test applications...")
        
        # Insert 50 random applications
        applications = []
        for _ in range(50):
            status = random.choice(STATUSES)
            app = JobApplication(
                company_name=fake.company(),
                job_title=fake.job(),
                source=random.choice(SOURCES),
                status=status,
                applied_date=date.today() - timedelta(days=random.randint(0, 60)),
                job_url=fake.url(),
                location=fake.city(),
                work_type=random.choice(WORK_TYPES),
                contact_name=fake.name(),
                contact_email=fake.company_email(),
                needs_review=random.random() < 0.2,  # ~20% flagged for review
            )
            session.add(app)
            applications.append(app)
            
        await session.commit()
        print("Done seeding user applications!")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(seed_database())
