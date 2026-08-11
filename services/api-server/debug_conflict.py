"""Debug script to understand conflict resolution issue."""
from datetime import UTC, datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, Task, User

# Create in-memory database
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()

# Create user
user = User(
    id="test-user",
    email="test@example.com",
    name="Test",
    password_hash="hash",
    email_verified=True,
)
session.add(user)
session.commit()

# Simulate the test scenario
create_time = datetime.now(UTC)
print(f"Create time: {create_time}")
print(f"Create time tzinfo: {create_time.tzinfo}")

# Step 1: Create task
task = Task(
    id="task-002",
    organization_id=None,
    created_by=user.id,
    title="Original Title",
    goal="Original goal",
    status="pending",
    model_provider="anthropic",
    model_name="claude-opus-4",
    created_at=create_time,
    updated_at=create_time,
)
session.add(task)
session.commit()

print(f"\nAfter create - Task updated_at: {task.updated_at}")
print(f"After create - Task updated_at tzinfo: {task.updated_at.tzinfo}")

# Step 2: Server update
server_update_time = create_time + timedelta(minutes=2)
print(f"\nServer update time: {server_update_time}")
print(f"Server update time tzinfo: {server_update_time.tzinfo}")

task.title = "Server Updated Title"
task.updated_at = server_update_time
session.commit()

print(f"After server update - Task updated_at: {task.updated_at}")
print(f"After server update - Task updated_at tzinfo: {task.updated_at.tzinfo}")

# Step 3: Attempt resolve with current time
resolve_time = datetime.now(UTC)
print(f"\nResolve time: {resolve_time}")
print(f"Resolve time tzinfo: {resolve_time.tzinfo}")

# Retrieve task fresh from database (simulating what the endpoint does)
from sqlalchemy import select
fresh_task = session.execute(select(Task).where(Task.id == "task-002")).scalar_one()

print(f"\nFresh task updated_at: {fresh_task.updated_at}")
print(f"Fresh task updated_at tzinfo: {fresh_task.updated_at.tzinfo}")

# Apply the fix from desktop_sync.py
server_updated_at = fresh_task.updated_at
if server_updated_at.tzinfo is None:
    server_updated_at = server_updated_at.replace(tzinfo=UTC)
    print(f"Fixed server_updated_at: {server_updated_at}")
    print(f"Fixed server_updated_at tzinfo: {server_updated_at.tzinfo}")

operation_timestamp = resolve_time
if operation_timestamp.tzinfo is None:
    operation_timestamp = operation_timestamp.replace(tzinfo=UTC)

print(f"\nComparison:")
print(f"  server_updated_at: {server_updated_at}")
print(f"  operation_timestamp: {operation_timestamp}")
print(f"  server_updated_at > operation_timestamp: {server_updated_at > operation_timestamp}")
print(f"  Should apply: {not (server_updated_at > operation_timestamp)}")
