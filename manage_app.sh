#!/bin/bash

# Script to manage the FastAPI app server and a separate web server (serve)
# Usage: ./manage_app.sh [start|stop|reload|status]

# Configuration
APP_DIR="/Users/craig/src/xplora"
UVICORN_CMD="uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
SERVE_CMD="serve public -p 3000" # Updated to use -p instead of --port
APP_PID_FILE="$APP_DIR/app.pid"
SERVE_PID_FILE="$APP_DIR/serve.pid"
APP_LOG_FILE="$APP_DIR/app.log"
SERVE_LOG_FILE="$APP_DIR/serve.log"

# Ensure we're in the app directory
cd "$APP_DIR" || {
  echo "Error: Could not change to directory $APP_DIR"
  exit 1
}

# Function to check if serve is installed
check_serve_installed() {
  if ! command -v serve > /dev/null 2>&1; then
    echo "Error: 'serve' is not installed. Please install it with 'npm install -g serve'."
    exit 1
  fi
}

# Function to check if the app server is running
check_app_running() {
  if [ -f "$APP_PID_FILE" ]; then
    APP_PID=$(cat "$APP_PID_FILE")
    if ps -p "$APP_PID" > /dev/null 2>&1; then
      return 0 # App server is running
    else
      # PID file exists, but process is not running; clean up
      rm -f "$APP_PID_FILE"
      return 1 # App server is not running
    fi
  else
    return 1 # App server is not running
  fi
}

# Function to check if the serve web server is running
check_serve_running() {
  if [ -f "$SERVE_PID_FILE" ]; then
    SERVE_PID=$(cat "$SERVE_PID_FILE")
    if ps -p "$SERVE_PID" > /dev/null 2>&1; then
      return 0 # Serve web server is running
    else
      # PID file exists, but process is not running; clean up
      rm -f "$SERVE_PID_FILE"
      return 1 # Serve web server is not running
    fi
  else
    return 1 # Serve web server is not running
  fi
}

# Function to start the app server
start_app() {
  if check_app_running; then
    echo "App server is already running with PID $(cat "$APP_PID_FILE")"
    return 1
  fi

  echo "Starting the app server..."
  # Run the app server in the background, redirect output to log file
  $UVICORN_CMD >> "$APP_LOG_FILE" 2>&1 &
  APP_PID=$!
  
  # Wait a moment to see if the process starts successfully
  sleep 2
  if ps -p "$APP_PID" > /dev/null 2>&1; then
    echo "$APP_PID" > "$APP_PID_FILE"
    echo "App server started successfully with PID $APP_PID"
    echo "App server logs are being written to $APP_LOG_FILE"
    echo "API accessible at http://127.0.0.1:8000"
  else
    echo "Error: Failed to start the app server. Check $APP_LOG_FILE for details."
    return 1
  fi
  return 0
}

# Function to start the serve web server
start_serve() {
  # Check if serve is installed
  check_serve_installed

  if check_serve_running; then
    echo "Serve web server is already running with PID $(cat "$SERVE_PID_FILE")"
    return 1
  fi

  echo "Starting the serve web server..."
  # Run the serve web server in the background, redirect output to log file
  $SERVE_CMD >> "$SERVE_LOG_FILE" 2>&1 &
  SERVE_PID=$!
  
  # Wait a moment to see if the process starts successfully
  sleep 2
  if ps -p "$SERVE_PID" > /dev/null 2>&1; then
    echo "$SERVE_PID" > "$SERVE_PID_FILE"
    echo "Serve web server started successfully with PID $SERVE_PID"
    echo "Serve web server logs are being written to $SERVE_LOG_FILE"
    echo "Frontend accessible at http://127.0.0.1:3000"
  else
    echo "Error: Failed to start the serve web server. Check $SERVE_LOG_FILE for details."
    return 1
  fi
  return 0
}

# Function to stop the app server
stop_app() {
  if ! check_app_running; then
    echo "App server is not running"
    return 1
  fi

  APP_PID=$(cat "$APP_PID_FILE")
  echo "Stopping the app server with PID $APP_PID..."
  kill -15 "$APP_PID" # SIGTERM for graceful shutdown

  # Wait for the process to terminate
  for i in {1..5}; do
    if ! ps -p "$APP_PID" > /dev/null 2>&1; then
      echo "App server stopped successfully"
      rm -f "$APP_PID_FILE"
      return 0
    fi
    sleep 1
  done

  # If still running, force kill
  echo "App server did not stop gracefully, forcing shutdown..."
  kill -9 "$APP_PID" 2>/dev/null
  if ! ps -p "$APP_PID" > /dev/null 2>&1; then
    echo "App server stopped successfully"
    rm -f "$APP_PID_FILE"
  else
    echo "Error: Failed to stop the app server with PID $APP_PID"
    return 1
  fi
  return 0
}

# Function to stop the serve web server
stop_serve() {
  if ! check_serve_running; then
    echo "Serve web server is not running"
    return 1
  fi

  SERVE_PID=$(cat "$SERVE_PID_FILE")
  echo "Stopping the serve web server with PID $SERVE_PID..."
  kill -15 "$SERVE_PID" # SIGTERM for graceful shutdown

  # Wait for the process to terminate
  for i in {1..5}; do
    if ! ps -p "$SERVE_PID" > /dev/null 2>&1; then
      echo "Serve web server stopped successfully"
      rm -f "$SERVE_PID_FILE"
      return 0
    fi
    sleep 1
  done

  # If still running, force kill
  echo "Serve web server did not stop gracefully, forcing shutdown..."
  kill -9 "$SERVE_PID" 2>/dev/null
  if ! ps -p "$SERVE_PID" > /dev/null 2>&1; then
    echo "Serve web server stopped successfully"
    rm -f "$SERVE_PID_FILE"
  else
    echo "Error: Failed to stop the serve web server with PID $SERVE_PID"
    return 1
  fi
  return 0
}

# Function to start both servers
start_all() {
  local app_status=0
  local serve_status=0

  start_app
  app_status=$?
  start_serve
  serve_status=$?

  if [ $app_status -eq 0 ] && [ $serve_status -eq 0 ]; then
    echo "Both servers started successfully"
  else
    echo "One or both servers failed to start. Check logs for details."
    exit 1
  fi
}

# Function to stop both servers
stop_all() {
  local app_status=0
  local serve_status=0

  if check_app_running; then
    stop_app
    app_status=$?
  else
    echo "App server was not running"
    app_status=0
  fi

  if check_serve_running; then
    stop_serve
    serve_status=$?
  else
    echo "Serve web server was not running"
    serve_status=0
  fi

  if [ $app_status -eq 0 ] && [ $serve_status -eq 0 ]; then
    echo "Both servers stopped successfully"
  else
    echo "One or both servers failed to stop properly"
    exit 1
  fi
}

# Function to reload both servers (stop and start)
reload_all() {
  stop_all
  start_all
}

# Function to check status of both servers
check_status() {
  if check_app_running; then
    APP_PID=$(cat "$APP_PID_FILE")
    echo "App server is running with PID $APP_PID"
    echo "API accessible at http://127.0.0.1:8000"
    echo "App server logs are available at $APP_LOG_FILE"
  else
    echo "App server is not running"
  fi

  if check_serve_running; then
    SERVE_PID=$(cat "$SERVE_PID_FILE")
    echo "Serve web server is running with PID $SERVE_PID"
    echo "Frontend accessible at http://127.0.0.1:3000"
    echo "Serve web server logs are available at $SERVE_LOG_FILE"
  else
    echo "Serve web server is not running"
  fi
}

# Main command handler
case "$1" in
  start)
    start_all
    ;;
  stop)
    stop_all
    ;;
  reload)
    reload_all
    ;;
  status)
    check_status
    ;;
  *)
    echo "Usage: $0 [start|stop|reload|status]"
    echo "  start  - Start both the app server and serve web server"
    echo "  stop   - Stop both the app server and serve web server"
    echo "  reload - Reload both servers (stop then start)"
    echo "  status - Check the status of both servers"
    exit 1
    ;;
esac

exit 0