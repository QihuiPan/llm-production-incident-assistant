# Payments API Runbook

## Elevated payment errors

First separate validation failures from dependency failures. A simultaneous increase in `http_error_rate` and `HTTP 503 returned by dependency payments-db` usually points to dependency availability or connection saturation. Review recent deployments before escalating.

## Safe queries

The approved investigation tools may read service logs, HTTP metrics, deployment metadata, and service dependencies. The assistant cannot retry charges, modify payment records, or restart a component.
