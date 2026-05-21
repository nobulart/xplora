#!/bin/bash

# Script to manage the FastAPI app server and a separate web server (serve)
# Usage: ./manage_app.sh [start|stop|reload|status]

# Configuration
APP_DIR="/Users/craig/src/xplora"
APP_PORT=8000
FRONTEND_PORT=3000
UVICORN_CMD=(uvicorn main:app --host 0.0.0.0 --port "$APP_PORT" --reload)
FRONTEND_CMD=(python3 -m http.server "$FRONTEND_PORT" --directory public --bind 127.0.0.1)
APP_PID_FILE="$APP_DIR/app.pid"
SERVE_PID_FILE="$APP_DIR/serve.pid"
APP_LOG_FILE="$APP_DIR/app.log"
SERVE_LOG_FILE="$APP_DIR/serve.log"

# Ensure we're in the app directory
cd "$APP_DIR" || {
  echo "Error: Could not change to directory $APP_DIR"
  exit 1
}

# Function to check whether required commands are available
check_dependencies() {
  if ! command -v uvicorn > /dev/null 2>&1; then
    echo "Error: 'uvicorn' is not installed or not on PATH."
    exit 1
  fi

  if ! command -v python3 > /dev/null 2>&1; then
    echo "Error: 'python3' is not installed or not on PATH."
    exit 1
  fi

  if ! command -v curl > /dev/null 2>&1; then
    echo "Error: 'curl' is not installed or not on PATH."
    exit 1
  fi
}

get_port_pid() {
  lsof -tiTCP:"$1" -sTCP:LISTEN 2>/dev/null | head -n 1
}

is_url_ready() {
  curl -fsS "$1" > /dev/null 2>&1
}

wait_for_url() {
  local url="$1"
  local pid="$2"
  local timeout="$3"

  for ((i = 1; i <= timeout; i++)); do
    if is_url_ready "$url"; then
      return 0
    fi

    if ! ps -p "$pid" > /dev/null 2>&1; then
      return 1
    fi

    sleep 1
  done

  return 1
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
  check_dependencies

  if check_app_running; then
    echo "App server is already running with PID $(cat "$APP_PID_FILE")"
    return 0
  fi

  EXISTING_PID=$(get_port_pid "$APP_PORT")
  if [ -n "$EXISTING_PID" ]; then
    if is_url_ready "http://127.0.0.1:$APP_PORT/health"; then
      echo "$EXISTING_PID" > "$APP_PID_FILE"
      echo "App server is already running with PID $EXISTING_PID"
      echo "API accessible at http://127.0.0.1:$APP_PORT"
      return 0
    fi
    echo "Error: Port $APP_PORT is already in use by PID $EXISTING_PID."
    echo "Stop that process or run './manage_app.sh stop' if it belongs to Xplora."
    return 1
  fi

  echo "Starting the app server..."
  # Run the app server in the background, redirect output to log file
  nohup "${UVICORN_CMD[@]}" >> "$APP_LOG_FILE" 2>&1 &
  APP_PID=$!
  
  if wait_for_url "http://127.0.0.1:$APP_PORT/health" "$APP_PID" 180; then
    echo "$APP_PID" > "$APP_PID_FILE"
    echo "App server started successfully with PID $APP_PID"
    echo "App server logs are being written to $APP_LOG_FILE"
    echo "API accessible at http://127.0.0.1:$APP_PORT"
  else
    echo "Error: Failed to start the app server. Check $APP_LOG_FILE for details."
    kill "$APP_PID" 2>/dev/null
    rm -f "$APP_PID_FILE"
    return 1
  fi
  return 0
}

# Function to start the serve web server
start_serve() {
  check_dependencies

  if check_serve_running; then
    echo "Serve web server is already running with PID $(cat "$SERVE_PID_FILE")"
    return 0
  fi

  EXISTING_PID=$(get_port_pid "$FRONTEND_PORT")
  if [ -n "$EXISTING_PID" ]; then
    if is_url_ready "http://127.0.0.1:$FRONTEND_PORT"; then
      echo "$EXISTING_PID" > "$SERVE_PID_FILE"
      echo "Serve web server is already running with PID $EXISTING_PID"
      echo "Frontend accessible at http://127.0.0.1:$FRONTEND_PORT"
      return 0
    fi
    echo "Error: Port $FRONTEND_PORT is already in use by PID $EXISTING_PID."
    echo "Stop that process or run './manage_app.sh stop' if it belongs to Xplora."
    return 1
  fi

  echo "Starting the serve web server..."
  # Run the serve web server in the background, redirect output to log file
  nohup "${FRONTEND_CMD[@]}" >> "$SERVE_LOG_FILE" 2>&1 &
  SERVE_PID=$!
  
  if wait_for_url "http://127.0.0.1:$FRONTEND_PORT" "$SERVE_PID" 15; then
    echo "$SERVE_PID" > "$SERVE_PID_FILE"
    echo "Serve web server started successfully with PID $SERVE_PID"
    echo "Serve web server logs are being written to $SERVE_LOG_FILE"
    echo "Frontend accessible at http://127.0.0.1:$FRONTEND_PORT"
  else
    echo "Error: Failed to start the serve web server. Check $SERVE_LOG_FILE for details."
    kill "$SERVE_PID" 2>/dev/null
    rm -f "$SERVE_PID_FILE"
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

  start_serve
  serve_status=$?
  start_app
  app_status=$?

  if [ $app_status -eq 0 ] && [ $serve_status -eq 0 ]; then
    echo "Both servers started successfully"
    echo "Frontend is available first at http://127.0.0.1:$FRONTEND_PORT"
    echo "Backend warmup progress is available at http://127.0.0.1:$APP_PORT/startup-status"
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
    echo "API accessible at http://127.0.0.1:$APP_PORT"
    echo "App server logs are available at $APP_LOG_FILE"
  else
    echo "App server is not running"
  fi

  if check_serve_running; then
    SERVE_PID=$(cat "$SERVE_PID_FILE")
    echo "Serve web server is running with PID $SERVE_PID"
    echo "Frontend accessible at http://127.0.0.1:$FRONTEND_PORT"
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
