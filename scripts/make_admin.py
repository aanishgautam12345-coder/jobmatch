"""One-time script: make a user admin."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text
from app.database import engine

email = sys.argv[1] if len(sys.argv) > 1 else "test@example.com"
conn = engine.connect()
result = conn.execute(text("UPDATE users SET is_admin = true WHERE email = :email RETURNING email, is_admin"), {"email": email})
for row in result:
    print(f"User: {row[0]}, is_admin: {row[1]}")
conn.commit()
conn.close()
