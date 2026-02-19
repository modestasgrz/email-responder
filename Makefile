## Makefile for Email Responder Project
#
# Development: ruff (lint/format), mypy (type check), pytest (test).
# Deployment: Docker → Artifact Registry → Cloud Run Jobs.
#
# Prerequisites (one-time):
#   gcloud auth login
#   gcloud auth configure-docker $(GCP_REGION)-docker.pkg.dev
#   gcloud artifacts repositories create $(JOB_NAME) \
#     --repository-format=docker --location=$(GCP_REGION)
#
# Tools required: uv, ruff, mypy, docker, gcloud CLI.

GCP_PROJECT  ?= $(shell gcloud config get-value project)
GCP_REGION   ?= us-central1
JOB_NAME     ?= email-responder
IMAGE        ?= $(GCP_REGION)-docker.pkg.dev/$(GCP_PROJECT)/$(JOB_NAME)/$(JOB_NAME)

.PHONY: help check fix test gcp-setup build deploy run stop

## Show help for each make target
help:
	@echo "Available commands:"
	@echo "  make check     - Run linting (ruff) and type checking (mypy)"
	@echo "  make fix       - Automatically fix style issues with ruff"
	@echo "  make test      - Run the pytest test suite"
	@echo "  make gcp-setup - One-time GCP setup (Artifact Registry + Docker auth)"
	@echo "  make build     - Build Docker image and push to Artifact Registry"
	@echo "  make deploy    - Build, push, and deploy Cloud Run Job"
	@echo "  make run       - Execute the Cloud Run Job now"
	@echo "  make stop      - Cancel a running Cloud Run Job execution"

## Run code quality checks: ruff and mypy
check:
	@echo "Running ruff linter..."
	uv run ruff check .
	@echo "Running mypy type checker..."
	uv run mypy .

## Automatically fix import ordering and formatting issues using ruff
fix:
	@echo "Fixing code style issues with ruff..."
	uv run ruff check --fix .

## Run the pytest test suite
test:
	@echo "Running tests..."
	uv run pytest tests/ -s -vv

## One-time GCP setup: create Artifact Registry repo and configure Docker auth
gcp-setup:
	@echo "Creating Artifact Registry repository..."
	gcloud artifacts repositories create $(JOB_NAME) \
		--repository-format=docker \
		--location=$(GCP_REGION) \
		--project=$(GCP_PROJECT) || true
	@echo "Configuring Docker auth for Artifact Registry..."
	gcloud auth configure-docker $(GCP_REGION)-docker.pkg.dev

## Build Docker image and push to Artifact Registry
build:
	@echo "Building Docker image..."
	docker build -t $(IMAGE) .
	@echo "Pushing image to Artifact Registry..."
	docker push $(IMAGE)

## Deploy Cloud Run Job from the pushed image
deploy: build
	@echo "Deploying Cloud Run Job..."
	gcloud run jobs deploy $(JOB_NAME) \
		--image $(IMAGE) \
		--region $(GCP_REGION) \
		--project $(GCP_PROJECT)

## Execute the Cloud Run Job now (one-off trigger)
run:
	@echo "Triggering Cloud Run Job execution..."
	gcloud run jobs execute $(JOB_NAME) \
		--region $(GCP_REGION) \
		--project $(GCP_PROJECT) \
		--wait

## Cancel a running Cloud Run Job execution
stop:
	@echo "Cancelling Cloud Run Job execution..."
	gcloud run jobs executions list \
		--job $(JOB_NAME) \
		--region $(GCP_REGION) \
		--project $(GCP_PROJECT) \
		--filter="status.completionTime IS NULL" \
		--format="value(name)" \
		--limit=1 \
	| xargs -I {} gcloud run jobs executions cancel {} \
		--region $(GCP_REGION) \
		--project $(GCP_PROJECT)
