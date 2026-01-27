#!/bin/bash
set -e

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL..."
while ! python -c "
import asyncio
import asyncpg
import os

async def check_db():
    try:
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'db'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'postgres'),
            password=os.getenv('POSTGRES_PASSWORD', 'postgres'),
            database=os.getenv('POSTGRES_DB', 'sip_tools')
        )
        await conn.close()
        return True
    except Exception as e:
        print(f'DB not ready: {e}')
        return False

exit(0 if asyncio.run(check_db()) else 1)
" 2>/dev/null; do
    echo "PostgreSQL is unavailable - sleeping"
    sleep 2
done
echo "PostgreSQL is up!"

# Wait for Redis to be ready (if configured)
if [ -n "$REDIS_URL" ]; then
    echo "Waiting for Redis..."
    while ! python -c "
import redis
import os
import sys
try:
    url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    r = redis.from_url(url)
    r.ping()
    sys.exit(0)
except Exception as e:
    print(f'Redis not ready: {e}')
    sys.exit(1)
" 2>&1; do
        echo "Redis is unavailable - sleeping"
        sleep 2
    done
    echo "Redis is up!"
fi

# Run database migrations
if [ "$RUN_MIGRATIONS" = "true" ]; then
    echo "Running database migrations..."
    cd /app
    alembic upgrade head
    echo "Migrations completed!"
fi

# Execute the main command
echo "Starting application..."
exec "$@"
