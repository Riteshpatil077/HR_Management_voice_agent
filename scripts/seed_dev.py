#!/usr/bin/env python
"""
Development Database Seeder

Seeds the PostgreSQL database with realistic mock data for local development:
- Tenants
- Employees (HR Service)
- Onboarding Plans
- Interviews
- Dummy Call Records
"""

import asyncio
import os
import uuid
from datetime import datetime, timezone, timedelta
from faker import Faker

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import text

DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql+asyncpg://hrvoice:hrvoice@localhost:5432/hrvoice"
)

fake = Faker()
engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)

async def seed_data() -> None:
    print("🌱 Starting database seeding...")
    
    async with AsyncSessionLocal() as session:
        # Create a Demo Tenant
        tenant_id = str(uuid.uuid4())
        print(f"Creating Tenant: {tenant_id}")
        
        # 1. Seed HR Data (Employees)
        departments = ["Engineering", "Sales", "HR", "Marketing"]
        employee_ids = []
        for _ in range(20):
            emp_id = str(uuid.uuid4())
            employee_ids.append(emp_id)
            await session.execute(
                text("""
                INSERT INTO employees (id, tenant_id, first_name, last_name, email, department, role, status, created_at, updated_at)
                VALUES (:id, :tenant_id, :first, :last, :email, :dept, :role, :status, :now, :now)
                """),
                {
                    "id": emp_id,
                    "tenant_id": tenant_id,
                    "first": fake.first_name(),
                    "last": fake.last_name(),
                    "email": fake.email(),
                    "dept": fake.random_element(departments),
                    "role": fake.job(),
                    "status": "active",
                    "now": datetime.now(timezone.utc)
                }
            )

        # 2. Seed Interview Data
        print("Creating Interviews...")
        for _ in range(5):
            await session.execute(
                text("""
                INSERT INTO interviews (id, tenant_id, candidate_name, candidate_email, role, scheduled_at, status, created_at, updated_at)
                VALUES (:id, :tenant_id, :name, :email, :role, :scheduled, :status, :now, :now)
                """),
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "name": fake.name(),
                    "email": fake.email(),
                    "role": "Software Engineer",
                    "scheduled": datetime.now(timezone.utc) + timedelta(days=fake.random_int(min=1, max=14)),
                    "status": "scheduled",
                    "now": datetime.now(timezone.utc)
                }
            )

        # 3. Seed Onboarding Data
        print("Creating Onboarding Plans...")
        for emp_id in employee_ids[:5]:
            plan_id = str(uuid.uuid4())
            await session.execute(
                text("""
                INSERT INTO onboarding_plans (id, tenant_id, employee_id, department_id, status, created_at, updated_at)
                VALUES (:id, :tenant_id, :emp, :dept, :status, :now, :now)
                """),
                {
                    "id": plan_id,
                    "tenant_id": tenant_id,
                    "emp": emp_id,
                    "dept": "Engineering",
                    "status": "in_progress",
                    "now": datetime.now(timezone.utc)
                }
            )
            # Add tasks
            for task in ["IT Setup", "HR Orientation", "Team Intro"]:
                await session.execute(
                    text("""
                    INSERT INTO onboarding_tasks (id, plan_id, name, description, status)
                    VALUES (:id, :plan, :name, :desc, :status)
                    """),
                    {
                        "id": str(uuid.uuid4()),
                        "plan": plan_id,
                        "name": task,
                        "desc": f"Description for {task}",
                        "status": fake.random_element(["pending", "completed"])
                    }
                )

        await session.commit()
        print("✅ Seeding complete!")

if __name__ == "__main__":
    asyncio.run(seed_data())
