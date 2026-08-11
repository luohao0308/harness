# ADR 0004: Use Docker Sandbox And WarmPool

## Status

accepted

## Context

Agent tools may run shell commands, tests, package installs and file writes. Host execution creates unacceptable security risk.

## Decision

High-risk tools execute inside Docker Sandbox. WarmPool maintains preheated containers for low-risk reusable execution paths.

## Consequences

- Host shell execution for Agent tools is forbidden.
- Docker SDK for Python manages containers.
- WarmPool target acquire latency is under 50ms on hit.
- High-risk tasks use single-use containers.

