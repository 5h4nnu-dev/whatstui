#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR/frontend"
exec "$DIR/venv/bin/python" app.py
