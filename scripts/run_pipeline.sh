#!/usr/bin/env bash
# =============================================================================
# scripts/run_pipeline.sh
# Runs the full pipeline in order: generate -> ingest -> load.
#
# `set -e` means the script stops immediately if any stage fails, instead
# of pressing on and loading garbage into the warehouse — e.g. if
# ingestion crashes, we do NOT want load.py to silently run against
# stale or partial Parquet files from a previous run.
# =============================================================================
set -e

echo "=================================================="
echo "[1/3] Generating synthetic raw data..."
echo "=================================================="
python -m lake.generate_data

echo ""
echo "=================================================="
echo "[2/3] Cleaning raw data (lake ingestion)..."
echo "=================================================="
python -m lake.ingest

echo ""
echo "=================================================="
echo "[3/3] Loading warehouse (Postgres)..."
echo "=================================================="
python -m warehouse.load

echo ""
echo "Pipeline complete. Warehouse is ready to query."
