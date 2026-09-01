# Inventory API Runbook

## Queue backlog

A rising queue depth with stable request rate usually indicates slow consumers or an unavailable inventory database. Correlate `queue_depth`, consumer error logs, and the deployment timeline.

## Investigation boundary

Only use read-only metrics, logs, deployment metadata, and service-catalog lookups. Queue purges and consumer restarts require a separate operator workflow.
