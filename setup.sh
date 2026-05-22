#!/bin/bash

# NeoNoble Ramp - Quick Setup Script
# This script sets up the database and initializes the platform

set -e

echo "🚀 NeoNoble Ramp - Quick Setup"
echo "================================"
echo ""

# Check if PostgreSQL is running
if ! pg_isready -h localhost -p 5432 2>/dev/null; then
    echo "❌ PostgreSQL is not running on localhost:5432"
    echo ""
    echo "Please start PostgreSQL first:"
    echo "  • Using Docker: docker compose up -d"
    echo "  • Using system service: sudo service postgresql start"
    echo ""
    exit 1
fi

echo "✅ PostgreSQL is running"
echo ""

# Generate Prisma client
echo "📦 Generating Prisma client..."
npx prisma generate

# Run migrations
echo "🗄️  Running database migrations..."
npx prisma migrate deploy

# Initialize database
echo "🔧 Initializing platform_internal API client..."
node scripts/initDatabase.js

echo ""
echo "✨ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Start the development server: yarn dev"
echo "2. Visit http://localhost:3000"
echo "3. Access Dev Portal: http://localhost:3000/dev/login"
echo "4. Access User Ramp: http://localhost:3000/ramp"
echo ""
