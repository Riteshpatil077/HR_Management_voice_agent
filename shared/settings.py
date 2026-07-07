"""
Application Settings.

All configuration sourced from environment variables (12-factor app).
In production, secrets are injected by HashiCorp Vault via Kubernetes
mutating webhook or environment variable injection.

Design Pattern: Singleton settings via lru_cache.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from pydantic import AnyHttpUrl, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """PostgreSQL database configuration."""

    model_config = SettingsConfigDict(env_prefix="DB_", extra="ignore")

    url: str = Field(default="", alias="DATABASE_URL")
    replica_1_url: str = Field(default="", alias="DATABASE_URL_REPLICA_1")
    replica_2_url: str = Field(default="", alias="DATABASE_URL_REPLICA_2")
    pool_size: int = Field(default=20, ge=1, le=100)
    max_overflow: int = Field(default=10, ge=0, le=50)
    pool_timeout: int = Field(default=30, ge=1)
    pool_recycle: int = Field(default=3600, ge=60)
    echo: bool = Field(default=False)

    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)


class RedisSettings(BaseSettings):
    """Redis Cluster configuration."""

    nodes: str = Field(
        default="localhost:7001,localhost:7002,localhost:7003,localhost:7004,localhost:7005,localhost:7006",
        alias="REDIS_NODES",
    )
    password: str = Field(default="", alias="REDIS_PASSWORD")
    ssl: bool = Field(default=False, alias="REDIS_SSL")
    default_ttl: int = Field(default=3600, alias="REDIS_DEFAULT_TTL")
    session_ttl: int = Field(default=1800, alias="REDIS_SESSION_TTL")
    cache_ttl: int = Field(default=300, alias="REDIS_CACHE_TTL")

    @property
    def node_list(self) -> list[dict[str, Any]]:
        """Parse comma-separated nodes into list of host/port dicts."""
        result = []
        for node in self.nodes.split(","):
            host, port = node.strip().split(":")
            result.append({"host": host, "port": int(port)})
        return result

    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)


class RabbitMQSettings(BaseSettings):
    """RabbitMQ configuration."""

    url: str = Field(
        default="amqp://guest:guest@localhost:5672/",
        alias="RABBITMQ_URL",
    )
    prefetch_count: int = Field(default=10, alias="RABBITMQ_PREFETCH_COUNT")
    heartbeat: int = Field(default=60, alias="RABBITMQ_HEARTBEAT")

    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)


class VaultSettings(BaseSettings):
    """HashiCorp Vault configuration."""

    addr: str = Field(default="http://localhost:8200", alias="VAULT_ADDR")
    token: str = Field(default="", alias="VAULT_TOKEN")
    role: str = Field(default="hr-voice-agent", alias="VAULT_ROLE")
    namespace: str = Field(default="", alias="VAULT_NAMESPACE")
    mount_path: str = Field(default="secret", alias="VAULT_MOUNT_PATH")
    pki_mount: str = Field(default="pki", alias="VAULT_PKI_MOUNT")
    pki_role: str = Field(default="hr-voice-agent", alias="VAULT_PKI_ROLE")

    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)


class OTELSettings(BaseSettings):
    """OpenTelemetry configuration."""

    exporter_endpoint: str = Field(
        default="http://localhost:4317",
        alias="OTEL_EXPORTER_OTLP_ENDPOINT",
    )
    service_name: str = Field(default="hr-voice-agent", alias="OTEL_SERVICE_NAME")
    traces_sampler: str = Field(
        default="parentbased_traceidratio",
        alias="OTEL_TRACES_SAMPLER",
    )
    traces_sampler_arg: float = Field(
        default=0.1,
        alias="OTEL_TRACES_SAMPLER_ARG",
        ge=0.0,
        le=1.0,
    )

    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)


class Settings(BaseSettings):
    """
    Master application settings.

    All values loaded from environment variables.
    Secrets are injected by Vault in production.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # ── Application ────────────────────────────────────────────────────────
    app_env: str = Field(default="development", alias="APP_ENV")
    app_name: str = Field(default="hr-voice-agent", alias="APP_NAME")
    app_version: str = Field(default="3.0.0", alias="APP_VERSION")
    debug: bool = Field(default=False, alias="DEBUG")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    workers: int = Field(default=4, ge=1, alias="WORKERS")
    port: int = Field(default=8000, ge=1024, le=65535, alias="PORT")
    service_name: str = Field(default="hr-voice-agent", alias="SERVICE_NAME")

    # ── Security ───────────────────────────────────────────────────────────
    secret_key: str = Field(default="", alias="SECRET_KEY")
    jwt_private_key_path: str = Field(default="", alias="JWT_PRIVATE_KEY_PATH")
    jwt_public_key_path: str = Field(default="", alias="JWT_PUBLIC_KEY_PATH")
    jwt_algorithm: str = Field(default="RS256", alias="JWT_ALGORITHM")
    jwt_access_expire_minutes: int = Field(
        default=30, ge=5, alias="JWT_ACCESS_TOKEN_EXPIRE_MINUTES"
    )
    jwt_refresh_expire_days: int = Field(
        default=7, ge=1, alias="JWT_REFRESH_TOKEN_EXPIRE_DAYS"
    )
    allowed_hosts: list[str] = Field(default=["*"], alias="ALLOWED_HOSTS")
    cors_origins: list[str] = Field(
        default=["http://localhost:3000"], alias="CORS_ORIGINS"
    )

    # ── External Services ──────────────────────────────────────────────────
    database_url: str = Field(default="", alias="DATABASE_URL")
    database_url_replica_1: str = Field(default="", alias="DATABASE_URL_REPLICA_1")
    database_url_replica_2: str = Field(default="", alias="DATABASE_URL_REPLICA_2")
    db_pool_size: int = Field(default=20, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=10, alias="DB_MAX_OVERFLOW")
    db_pool_timeout: int = Field(default=30, alias="DB_POOL_TIMEOUT")
    db_pool_recycle: int = Field(default=3600, alias="DB_POOL_RECYCLE")
    db_echo: bool = Field(default=False, alias="DB_ECHO")

    redis_nodes: str = Field(
        default="localhost:7001,localhost:7002,localhost:7003",
        alias="REDIS_NODES",
    )
    redis_password: str = Field(default="", alias="REDIS_PASSWORD")
    redis_ssl: bool = Field(default=False, alias="REDIS_SSL")
    redis_default_ttl: int = Field(default=3600, alias="REDIS_DEFAULT_TTL")
    redis_session_ttl: int = Field(default=1800, alias="REDIS_SESSION_TTL")
    redis_cache_ttl: int = Field(default=300, alias="REDIS_CACHE_TTL")

    rabbitmq_url: str = Field(
        default="amqp://guest:guest@localhost:5672/",
        alias="RABBITMQ_URL",
    )
    rabbitmq_prefetch_count: int = Field(default=10, alias="RABBITMQ_PREFETCH_COUNT")
    rabbitmq_heartbeat: int = Field(default=60, alias="RABBITMQ_HEARTBEAT")

    vault_addr: str = Field(default="http://localhost:8200", alias="VAULT_ADDR")
    vault_token: str = Field(default="", alias="VAULT_TOKEN")
    vault_role: str = Field(default="hr-voice-agent", alias="VAULT_ROLE")
    vault_namespace: str = Field(default="", alias="VAULT_NAMESPACE")
    vault_mount_path: str = Field(default="secret", alias="VAULT_MOUNT_PATH")

    opa_url: str = Field(default="http://localhost:8181", alias="OPA_URL")
    opa_policy_path: str = Field(default="hr_voice/authz", alias="OPA_POLICY_PATH")
    opa_timeout: int = Field(default=5, alias="OPA_TIMEOUT")

    # ── LLM Providers ─────────────────────────────────────────────────────
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o", alias="OPENAI_MODEL")
    openai_mini_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MINI_MODEL")
    openai_timeout: int = Field(default=30, alias="OPENAI_TIMEOUT")

    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(
        default="claude-3-5-sonnet-20241022", alias="ANTHROPIC_MODEL"
    )
    anthropic_timeout: int = Field(default=30, alias="ANTHROPIC_TIMEOUT")

    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-1.5-flash", alias="GEMINI_MODEL")
    gemini_pro_model: str = Field(default="gemini-1.5-pro", alias="GEMINI_PRO_MODEL")
    gemini_timeout: int = Field(default=30, alias="GEMINI_TIMEOUT")

    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="llama3.1:8b", alias="OLLAMA_MODEL")
    ollama_timeout: int = Field(default=60, alias="OLLAMA_TIMEOUT")

    # ── Voice AI ───────────────────────────────────────────────────────────
    deepgram_api_key: str = Field(default="", alias="DEEPGRAM_API_KEY")
    deepgram_timeout: int = Field(default=60, alias="DEEPGRAM_TIMEOUT")

    elevenlabs_api_key: str = Field(default="", alias="ELEVENLABS_API_KEY")
    elevenlabs_default_voice_id: str = Field(
        default="", alias="ELEVENLABS_DEFAULT_VOICE_ID"
    )
    elevenlabs_model_id: str = Field(
        default="eleven_multilingual_v2", alias="ELEVENLABS_MODEL_ID"
    )
    elevenlabs_timeout: int = Field(default=30, alias="ELEVENLABS_TIMEOUT")

    # ── Telephony ─────────────────────────────────────────────────────────
    exotel_sid: str = Field(default="", alias="EXOTEL_SID")
    exotel_api_key: str = Field(default="", alias="EXOTEL_API_KEY")
    exotel_api_token: str = Field(default="", alias="EXOTEL_API_TOKEN")
    exotel_subdomain: str = Field(default="api.exotel.com", alias="EXOTEL_SUBDOMAIN")
    exotel_from_number: str = Field(default="", alias="EXOTEL_FROM_NUMBER")
    exotel_webhook_hmac_secret: str = Field(
        default="", alias="EXOTEL_WEBHOOK_HMAC_SECRET"
    )

    twilio_account_sid: str = Field(default="", alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str = Field(default="", alias="TWILIO_AUTH_TOKEN")
    twilio_from_number: str = Field(default="", alias="TWILIO_FROM_NUMBER")

    # ── Messaging ─────────────────────────────────────────────────────────
    meta_whatsapp_token: str = Field(default="", alias="META_WHATSAPP_TOKEN")
    meta_whatsapp_phone_number_id: str = Field(
        default="", alias="META_WHATSAPP_PHONE_NUMBER_ID"
    )
    meta_whatsapp_business_account_id: str = Field(
        default="", alias="META_WHATSAPP_BUSINESS_ACCOUNT_ID"
    )
    meta_whatsapp_webhook_verify_token: str = Field(
        default="", alias="META_WHATSAPP_WEBHOOK_VERIFY_TOKEN"
    )
    meta_whatsapp_app_secret: str = Field(default="", alias="META_WHATSAPP_APP_SECRET")
    meta_whatsapp_api_version: str = Field(
        default="v19.0", alias="META_WHATSAPP_API_VERSION"
    )

    # ── Calendar ──────────────────────────────────────────────────────────
    google_client_id: str = Field(default="", alias="GOOGLE_CLIENT_ID")
    google_client_secret: str = Field(default="", alias="GOOGLE_CLIENT_SECRET")
    google_redirect_uri: str = Field(default="", alias="GOOGLE_REDIRECT_URI")

    microsoft_client_id: str = Field(default="", alias="MICROSOFT_CLIENT_ID")
    microsoft_client_secret: str = Field(default="", alias="MICROSOFT_CLIENT_SECRET")
    microsoft_tenant_id: str = Field(default="", alias="MICROSOFT_TENANT_ID")
    microsoft_redirect_uri: str = Field(default="", alias="MICROSOFT_REDIRECT_URI")

    # ── CRM ───────────────────────────────────────────────────────────────
    hubspot_access_token: str = Field(default="", alias="HUBSPOT_ACCESS_TOKEN")
    hubspot_webhook_secret: str = Field(default="", alias="HUBSPOT_WEBHOOK_SECRET")

    salesforce_username: str = Field(default="", alias="SALESFORCE_USERNAME")
    salesforce_password: str = Field(default="", alias="SALESFORCE_PASSWORD")
    salesforce_security_token: str = Field(
        default="", alias="SALESFORCE_SECURITY_TOKEN"
    )
    salesforce_domain: str = Field(
        default="login.salesforce.com", alias="SALESFORCE_DOMAIN"
    )

    zoho_client_id: str = Field(default="", alias="ZOHO_CLIENT_ID")
    zoho_client_secret: str = Field(default="", alias="ZOHO_CLIENT_SECRET")
    zoho_refresh_token: str = Field(default="", alias="ZOHO_REFRESH_TOKEN")
    zoho_region: str = Field(default="IN", alias="ZOHO_REGION")

    # ── AWS ───────────────────────────────────────────────────────────────
    aws_region: str = Field(default="ap-south-1", alias="AWS_REGION")
    aws_dr_region: str = Field(default="ap-southeast-1", alias="AWS_DR_REGION")
    aws_s3_bucket: str = Field(default="hr-voice-agent-prod", alias="AWS_S3_BUCKET")
    aws_s3_bucket_dr: str = Field(
        default="hr-voice-agent-dr", alias="AWS_S3_BUCKET_DR"
    )
    aws_kms_key_id: str = Field(default="", alias="AWS_KMS_KEY_ID")

    # ── Observability ─────────────────────────────────────────────────────
    otel_exporter_endpoint: str = Field(
        default="http://localhost:4317",
        alias="OTEL_EXPORTER_OTLP_ENDPOINT",
    )
    otel_service_name: str = Field(
        default="hr-voice-agent", alias="OTEL_SERVICE_NAME"
    )
    otel_traces_sampler_arg: float = Field(
        default=0.1, alias="OTEL_TRACES_SAMPLER_ARG"
    )

    langsmith_api_key: str = Field(default="", alias="LANGSMITH_API_KEY")
    langsmith_project: str = Field(
        default="hr-voice-agent-prod", alias="LANGSMITH_PROJECT"
    )

    # ── Feature Flags ─────────────────────────────────────────────────────
    feature_voice_clone_enabled: bool = Field(
        default=True, alias="FEATURE_VOICE_CLONE_ENABLED"
    )
    feature_whatsapp_enabled: bool = Field(
        default=True, alias="FEATURE_WHATSAPP_ENABLED"
    )
    feature_multi_llm_routing: bool = Field(
        default=True, alias="FEATURE_MULTI_LLM_ROUTING"
    )
    feature_audit_log_enabled: bool = Field(
        default=True, alias="FEATURE_AUDIT_LOG_ENABLED"
    )
    feature_cost_tracking_enabled: bool = Field(
        default=True, alias="FEATURE_COST_TRACKING_ENABLED"
    )

    # ── Rate Limiting ─────────────────────────────────────────────────────
    rate_limit_default: str = Field(default="100/minute", alias="RATE_LIMIT_DEFAULT")
    rate_limit_voice: str = Field(default="20/minute", alias="RATE_LIMIT_VOICE")
    rate_limit_auth: str = Field(default="10/minute", alias="RATE_LIMIT_AUTH")
    rate_limit_webhook: str = Field(
        default="500/minute", alias="RATE_LIMIT_WEBHOOK"
    )

    @field_validator("allowed_hosts", "cors_origins", mode="before")
    @classmethod
    def parse_comma_separated(cls, v: Any) -> list[str]:
        """Parse comma-separated string into list."""
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        """Enforce required settings in production environment."""
        if self.app_env == "production":
            required_secrets = [
                ("secret_key", "SECRET_KEY"),
                ("database_url", "DATABASE_URL"),
                ("openai_api_key", "OPENAI_API_KEY"),
                ("deepgram_api_key", "DEEPGRAM_API_KEY"),
                ("elevenlabs_api_key", "ELEVENLABS_API_KEY"),
            ]
            for attr, env_var in required_secrets:
                if not getattr(self, attr):
                    raise ValueError(
                        f"{env_var} is required in production environment"
                    )
        return self

    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development."""
        return self.app_env == "development"

    @property
    def redis_node_list(self) -> list[dict[str, Any]]:
        """Parse Redis nodes string into list of host/port dicts."""
        result = []
        for node in self.redis_nodes.split(","):
            host, port_str = node.strip().split(":")
            result.append({"host": host, "port": int(port_str)})
        return result

    @property
    def jwt_private_key(self) -> str:
        """Read JWT private key from file or Vault."""
        if self.jwt_private_key_path and os.path.exists(self.jwt_private_key_path):
            with open(self.jwt_private_key_path) as f:
                return f.read()
        return os.environ.get("JWT_PRIVATE_KEY", "")

    @property
    def jwt_public_key(self) -> str:
        """Read JWT public key from file or Vault."""
        if self.jwt_public_key_path and os.path.exists(self.jwt_public_key_path):
            with open(self.jwt_public_key_path) as f:
                return f.read()
        return os.environ.get("JWT_PUBLIC_KEY", "")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return cached application settings.

    Uses lru_cache to ensure a single Settings instance per process.
    Call get_settings.cache_clear() in tests to reset between test cases.
    """
    return Settings()
