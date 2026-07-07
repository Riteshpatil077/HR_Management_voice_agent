"""
HashiCorp Vault async client.

Provides:
- Dynamic secret retrieval with caching and auto-renewal
- PKI certificate generation for mTLS
- Database dynamic credential generation
- Secret rotation trigger
- Kubernetes auth method for production

All secrets in the platform MUST be retrieved through this module.
Direct environment variable access for secrets is forbidden in production.

Design Pattern: Singleton + Facade
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

import hvac
import structlog
from hvac.exceptions import Forbidden, InvalidPath, VaultError

from shared.settings import get_settings

logger = structlog.get_logger("vault.client")
settings = get_settings()


class SecretNotFoundError(Exception):
    """Raised when a secret path does not exist in Vault."""


class VaultAuthError(Exception):
    """Raised when Vault authentication fails."""


class CachedSecret:
    """Secret value with TTL-based cache expiry."""

    def __init__(self, value: dict[str, Any], ttl_seconds: int = 300) -> None:
        self.value = value
        self._expires_at = time.monotonic() + ttl_seconds

    def is_expired(self) -> bool:
        """Return True if cache entry has expired."""
        return time.monotonic() > self._expires_at


class VaultClient:
    """
    Async-compatible HashiCorp Vault client.

    Wraps the synchronous hvac library with asyncio thread pool execution.
    Implements secret caching, automatic token renewal, and PKI cert management.
    """

    def __init__(self) -> None:
        self._client: hvac.Client | None = None
        self._cache: dict[str, CachedSecret] = {}
        self._lock = asyncio.Lock()
        self._token_renew_task: asyncio.Task | None = None  # type: ignore[type-arg]

    async def initialize(self) -> None:
        """
        Initialize Vault client and authenticate.

        Uses Kubernetes service account in production,
        token auth in development.
        """
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._sync_initialize)
        logger.info("vault_client_initialized", addr=settings.vault_addr)

        # Schedule token renewal task
        self._token_renew_task = asyncio.create_task(self._token_renewal_loop())

    def _sync_initialize(self) -> None:
        """Synchronous Vault client initialization."""
        self._client = hvac.Client(
            url=settings.vault_addr,
            namespace=settings.vault_namespace or None,
        )

        if settings.is_production:
            self._kubernetes_auth()
        else:
            self._token_auth()

        if not self._client.is_authenticated():
            raise VaultAuthError(
                f"Vault authentication failed at {settings.vault_addr}"
            )

    def _token_auth(self) -> None:
        """Authenticate with static token (development only)."""
        if not self._client:
            raise VaultAuthError("Vault client not initialized")
        self._client.token = settings.vault_token
        logger.warning(
            "vault_token_auth",
            message="Using static token auth — development only. Use Kubernetes auth in production.",
        )

    def _kubernetes_auth(self) -> None:
        """Authenticate via Kubernetes service account JWT."""
        if not self._client:
            raise VaultAuthError("Vault client not initialized")
        try:
            with open("/var/run/secrets/kubernetes.io/serviceaccount/token") as f:
                jwt_token = f.read().strip()
            result = self._client.auth.kubernetes.login(
                role=settings.vault_role,
                jwt=jwt_token,
            )
            self._client.token = result["auth"]["client_token"]
            logger.info(
                "vault_kubernetes_auth_success",
                role=settings.vault_role,
                lease_duration=result["auth"]["lease_duration"],
            )
        except FileNotFoundError as exc:
            raise VaultAuthError(
                "Kubernetes service account token not found. "
                "Is the pod running in Kubernetes?"
            ) from exc

    async def _token_renewal_loop(self) -> None:
        """Periodically renew the Vault token before it expires."""
        while True:
            await asyncio.sleep(3600)  # Renew every hour
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._renew_token)
                logger.info("vault_token_renewed")
            except Exception as exc:
                logger.error("vault_token_renewal_failed", error=str(exc))

    def _renew_token(self) -> None:
        """Synchronously renew the Vault token."""
        if self._client and self._client.is_authenticated():
            self._client.auth.token.renew_self()

    async def get_secret(self, path: str, key: str | None = None) -> Any:
        """
        Retrieve a secret from Vault with caching.

        Args:
            path: Vault KV path (e.g., "services/voice-service/credentials")
            key: Specific key within the secret dict. Returns full dict if None.

        Returns:
            Secret value or full dict.

        Raises:
            SecretNotFoundError: If path or key does not exist.
            VaultAuthError: If authentication fails.
        """
        cache_key = f"{path}:{key or '*'}"

        async with self._lock:
            cached = self._cache.get(cache_key)
            if cached and not cached.is_expired():
                return cached.value.get(key) if key else cached.value

        loop = asyncio.get_event_loop()
        try:
            secret_data = await loop.run_in_executor(
                None, self._read_secret, path
            )
        except InvalidPath as exc:
            raise SecretNotFoundError(f"Secret not found at path: {path}") from exc
        except Forbidden as exc:
            raise VaultAuthError(
                f"Permission denied reading secret at: {path}"
            ) from exc

        async with self._lock:
            self._cache[cache_key] = CachedSecret(secret_data, ttl_seconds=300)

        logger.info("vault_secret_retrieved", path=path, key=key or "all")

        if key:
            if key not in secret_data:
                raise SecretNotFoundError(f"Key '{key}' not found in secret at: {path}")
            return secret_data[key]
        return secret_data

    def _read_secret(self, path: str) -> dict[str, Any]:
        """Synchronous KV v2 secret read."""
        if not self._client:
            raise VaultAuthError("Vault client not initialized")

        full_path = f"{settings.vault_mount_path}/{path}"
        response = self._client.secrets.kv.v2.read_secret_version(
            path=path,
            mount_point=settings.vault_mount_path,
        )
        data: dict[str, Any] = response["data"]["data"]
        return data

    async def put_secret(self, path: str, secret: dict[str, Any]) -> None:
        """
        Write a secret to Vault.

        Args:
            path: Vault KV path
            secret: Dict of key-value pairs to store
        """
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._write_secret, path, secret)

        # Invalidate cache
        async with self._lock:
            keys_to_delete = [k for k in self._cache if k.startswith(f"{path}:")]
            for key in keys_to_delete:
                del self._cache[key]

        logger.info("vault_secret_written", path=path)

    def _write_secret(self, path: str, secret: dict[str, Any]) -> None:
        """Synchronous KV v2 secret write."""
        if not self._client:
            raise VaultAuthError("Vault client not initialized")

        self._client.secrets.kv.v2.create_or_update_secret(
            path=path,
            secret=secret,
            mount_point=settings.vault_mount_path,
        )

    async def delete_secret(self, path: str) -> None:
        """Delete all versions of a secret at the given path."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._delete_secret, path)

        async with self._lock:
            keys_to_delete = [k for k in self._cache if k.startswith(f"{path}:")]
            for key in keys_to_delete:
                del self._cache[key]

        logger.info("vault_secret_deleted", path=path)

    def _delete_secret(self, path: str) -> None:
        """Synchronous secret deletion."""
        if not self._client:
            raise VaultAuthError("Vault client not initialized")
        self._client.secrets.kv.v2.delete_metadata_and_all_versions(
            path=path,
            mount_point=settings.vault_mount_path,
        )

    async def issue_certificate(
        self,
        common_name: str,
        ttl: str = "24h",
    ) -> dict[str, str]:
        """
        Issue a PKI certificate for mTLS.

        Args:
            common_name: Certificate CN (e.g., "voice-service.hr-voice-agent.svc.cluster.local")
            ttl: Certificate TTL (e.g., "24h", "168h")

        Returns:
            Dict with keys: certificate, private_key, ca_chain, serial_number
        """
        loop = asyncio.get_event_loop()
        cert_data = await loop.run_in_executor(
            None, self._issue_certificate, common_name, ttl
        )
        logger.info(
            "vault_certificate_issued",
            common_name=common_name,
            ttl=ttl,
            serial=cert_data.get("serial_number"),
        )
        return cert_data

    def _issue_certificate(self, common_name: str, ttl: str) -> dict[str, str]:
        """Synchronous certificate issuance."""
        if not self._client:
            raise VaultAuthError("Vault client not initialized")

        response = self._client.secrets.pki.generate_certificate(
            name=settings.vault_pki_role if hasattr(settings, "vault_pki_role") else "hr-voice-agent",
            common_name=common_name,
            extra_params={"ttl": ttl},
            mount_point=settings.vault_mount_path,
        )
        data: dict[str, Any] = response["data"]
        return {
            "certificate": data.get("certificate", ""),
            "private_key": data.get("private_key", ""),
            "ca_chain": "\n".join(data.get("ca_chain", [])),
            "serial_number": data.get("serial_number", ""),
            "expiration": str(data.get("expiration", "")),
        }

    async def generate_database_credentials(
        self, role: str
    ) -> dict[str, str]:
        """
        Generate dynamic database credentials via Vault database secrets engine.

        Args:
            role: Vault database role (e.g., "hrvoice-readonly", "hrvoice-readwrite")

        Returns:
            Dict with keys: username, password, lease_id, lease_duration
        """
        loop = asyncio.get_event_loop()
        creds = await loop.run_in_executor(
            None, self._generate_db_creds, role
        )
        logger.info(
            "vault_db_creds_generated",
            role=role,
            username=creds.get("username"),
            lease_duration=creds.get("lease_duration"),
        )
        return creds

    def _generate_db_creds(self, role: str) -> dict[str, str]:
        """Synchronous database credential generation."""
        if not self._client:
            raise VaultAuthError("Vault client not initialized")

        response = self._client.secrets.database.generate_credentials(name=role)
        return {
            "username": response["data"]["username"],
            "password": response["data"]["password"],
            "lease_id": response["lease_id"],
            "lease_duration": str(response["lease_duration"]),
        }

    async def rotate_secret(self, path: str, new_secret: dict[str, Any]) -> None:
        """
        Rotate a secret: write new value and invalidate all caches.

        Used by the secret rotation script and automated rotation jobs.
        """
        await self.put_secret(path, new_secret)
        logger.info("vault_secret_rotated", path=path)

    async def health_check(self) -> dict[str, Any]:
        """Check Vault server health status."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._health_check)

    def _health_check(self) -> dict[str, Any]:
        """Synchronous health check."""
        if not self._client:
            return {"status": "uninitialized"}
        try:
            status = self._client.sys.read_health_status()
            return {
                "status": "healthy" if not status.get("sealed") else "sealed",
                "initialized": status.get("initialized"),
                "sealed": status.get("sealed"),
                "version": status.get("version"),
            }
        except Exception as exc:
            return {"status": "unhealthy", "error": str(exc)}

    async def close(self) -> None:
        """Shutdown the client and cancel renewal task."""
        if self._token_renew_task:
            self._token_renew_task.cancel()
            try:
                await self._token_renew_task
            except asyncio.CancelledError:
                pass
        logger.info("vault_client_closed")


@lru_cache(maxsize=1)
def get_vault_client() -> VaultClient:
    """Return the singleton VaultClient instance."""
    return VaultClient()
