# Dockerfile to create a pre-built base image with all system dependencies.
# This is used to avoid network-related failures during the main application build.
#
# To build and push this image (for maintainers):
# docker build -t your-dockerhub-username/coincompare-base:1.0.0 -f prebuild.Dockerfile .
# docker push your-dockerhub-username/coincompare-base:1.0.0

# Start from the stable Debian "bookworm" release.
FROM python:3.10-slim-bookworm

# Install system dependencies
# This is the step that was failing due to network issues.
# By pre-building this, users can just pull the finished image.
RUN apt-get update && \
    apt-get install -y --fix-missing \
    build-essential \
    curl \
    libpq-dev \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*
