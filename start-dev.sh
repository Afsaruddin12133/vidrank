#!/bin/bash
# VidRank Development Environment Startup Script
# Starts both backend and frontend servers

set -e

BACKEND_DIR="backend"
FRONTEND_DIR="backend/frontend"
BACKEND_PORT=8787
FRONTEND_PORT=5173

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}VidRank Development Environment${NC}"
echo -e "${BLUE}========================================${NC}\n"

# Function to check if a port is in use
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1 ; then
        return 0
    else
        return 1
    fi
}

# Function to wait for a service to be ready
wait_for_service() {
    local url=$1
    local name=$2
    local max_attempts=30
    local attempt=0

    echo -e "${YELLOW}Waiting for $name to be ready...${NC}"
    
    while [ $attempt -lt $max_attempts ]; do
        if curl -s "$url" > /dev/null 2>&1; then
            echo -e "${GREEN}✓ $name is ready${NC}"
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 1
    done
    
    echo -e "${RED}✗ $name failed to start${NC}"
    return 1
}

# Check prerequisites
echo -e "${YELLOW}Checking prerequisites...${NC}"

if ! command -v uv &> /dev/null; then
    echo -e "${RED}✗ uv is not installed${NC}"
    echo "Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi
echo -e "${GREEN}✓ uv is installed${NC}"

if ! command -v npm &> /dev/null; then
    echo -e "${RED}✗ npm is not installed${NC}"
    exit 1
fi
echo -e "${GREEN}✓ npm is installed${NC}"

# Check if database exists
if [ ! -d "$BACKEND_DIR/.wrangler/state/v3/d1/miniflare-D1DatabaseObject" ]; then
    echo -e "${YELLOW}⚠ D1 database not initialized${NC}"
    echo "Run: cd $BACKEND_DIR && wrangler d1 execute vidrank --local --file=migrations/001_init.sql"
fi

# Start backend
echo -e "\n${BLUE}Starting backend server...${NC}"

if check_port $BACKEND_PORT; then
    echo -e "${YELLOW}⚠ Backend port $BACKEND_PORT is already in use${NC}"
    echo -e "Kill existing process? (y/n)"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        pkill -f "dev_server.py" || true
        sleep 2
    else
        echo -e "${YELLOW}Skipping backend startup${NC}"
        BACKEND_RUNNING=true
    fi
fi

if [ "$BACKEND_RUNNING" != "true" ]; then
    cd "$BACKEND_DIR"
    echo -e "${YELLOW}Installing backend dependencies...${NC}"
    uv sync --group dev > /dev/null 2>&1
    
    echo -e "${YELLOW}Starting backend on port $BACKEND_PORT...${NC}"
    nohup uv run python dev_server.py > dev_server.log 2>&1 &
    BACKEND_PID=$!
    cd - > /dev/null
    
    if wait_for_service "http://localhost:$BACKEND_PORT/healthz" "Backend"; then
        echo -e "${GREEN}✓ Backend started (PID: $BACKEND_PID)${NC}"
    else
        echo -e "${RED}✗ Backend failed to start${NC}"
        echo "Check logs: tail -f $BACKEND_DIR/dev_server.log"
        exit 1
    fi
fi

# Start frontend
echo -e "\n${BLUE}Starting frontend server...${NC}"

if check_port $FRONTEND_PORT; then
    echo -e "${YELLOW}⚠ Frontend port $FRONTEND_PORT is already in use${NC}"
    echo -e "Kill existing process? (y/n)"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        pkill -f "vite" || true
        sleep 2
    else
        echo -e "${YELLOW}Skipping frontend startup${NC}"
        FRONTEND_RUNNING=true
    fi
fi

if [ "$FRONTEND_RUNNING" != "true" ]; then
    cd "$FRONTEND_DIR"
    
    if [ ! -d "node_modules" ]; then
        echo -e "${YELLOW}Installing frontend dependencies...${NC}"
        npm install
    fi
    
    echo -e "${YELLOW}Starting frontend on port $FRONTEND_PORT...${NC}"
    nohup npm run dev > frontend.log 2>&1 &
    FRONTEND_PID=$!
    cd - > /dev/null
    
    if wait_for_service "http://localhost:$FRONTEND_PORT" "Frontend"; then
        echo -e "${GREEN}✓ Frontend started (PID: $FRONTEND_PID)${NC}"
    else
        echo -e "${RED}✗ Frontend failed to start${NC}"
        echo "Check logs: tail -f $FRONTEND_DIR/frontend.log"
        exit 1
    fi
fi

# Print summary
echo -e "\n${BLUE}========================================${NC}"
echo -e "${BLUE}Services Started${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✓ Backend:  ${NC}http://localhost:$BACKEND_PORT"
echo -e "${GREEN}✓ Frontend: ${NC}http://localhost:$FRONTEND_PORT"
echo -e "${GREEN}✓ Admin:    ${NC}http://localhost:$FRONTEND_PORT (login with password: admin123)"
echo -e "\n${YELLOW}Logs:${NC}"
echo -e "  Backend:  tail -f $BACKEND_DIR/dev_server.log"
echo -e "  Frontend: tail -f $FRONTEND_DIR/frontend.log"
echo -e "\n${YELLOW}Stop services:${NC}"
echo -e "  pkill -f 'dev_server.py'"
echo -e "  pkill -f 'vite'"
echo -e "${BLUE}========================================${NC}\n"
