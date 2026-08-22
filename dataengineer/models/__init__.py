
# Model wrappers for different LLM providers
# This package contains implementations for various LLM providers

# Apply SDK patches early, before any agents SDK usage
# This must happen before importing base.py or any other module that uses agents SDK
from dataengineer.models.sdk_patches import apply_sdk_patches

apply_sdk_patches()
