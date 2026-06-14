"""
Validation Service - Story 2.1 & 2.2: System and Configuration Validation

Handles validation checks for:
- System requirements (Python, Node, disk, memory)
- Configuration validation (secrets, database, API URLs, CORS)
- Service health checks
"""
from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Literal, TypedDict

import httpx
import psutil
from sqlalchemy import text

from app.core.config import (
    AUTH_JWT_SECRET_PLACEHOLDER,
    HARNESS_SECRET_ENCRYPTION_KEY_PLACEHOLDER,
    get_settings,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.core.config import Settings


ValidationStatus = Literal["pass", "warn", "fail"]


class ValidationResult(TypedDict):
    """Single validation check result."""

    check: str
    status: ValidationStatus
    message: str
    details: dict[str, str | int | bool] | None


class ValidationService:
    """
    Service for validating system requirements and configuration.

    This service handles:
    - Configuration validation (secrets, database, API URLs, CORS)
    - Future: System requirements checks (Python, Node, disk, memory)
    - Future: Service health checks
    """

    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        """Initialize validation service with database session."""
        self.session = session
        self.settings = settings or get_settings()

    def validate_all_system(self) -> list[ValidationResult]:
        """
        Run all system requirement validation checks.

        Returns:
            List of validation results for all system checks
        """
        results: list[ValidationResult] = []

        results.append(self.check_python_version())
        results.append(self.check_nodejs_version())
        results.append(self.check_disk_space())
        results.append(self.check_memory())

        return results

    def check_python_version(self) -> ValidationResult:
        """
        Check Python version (≥ 3.11).

        Returns:
            ValidationResult for Python version check
        """
        required_major = 3
        required_minor = 11

        try:
            result = subprocess.run(
                ["python3", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                return {
                    "check": "python_version",
                    "status": "fail",
                    "message": f"Failed to check Python version: {result.stderr}",
                    "details": {"error": result.stderr},
                }

            # Parse version from output like "Python 3.11.5"
            version_str = result.stdout.strip()
            version_parts = version_str.split()
            if len(version_parts) < 2:
                return {
                    "check": "python_version",
                    "status": "fail",
                    "message": f"Could not parse Python version from: {version_str}",
                    "details": {"output": version_str},
                }

            version = version_parts[1]
            version_numbers = version.split(".")
            if len(version_numbers) < 2:
                return {
                    "check": "python_version",
                    "status": "fail",
                    "message": f"Invalid Python version format: {version}",
                    "details": {"version": version},
                }

            major = int(version_numbers[0])
            minor = int(version_numbers[1])

            if major > required_major or (major == required_major and minor >= required_minor):
                return {
                    "check": "python_version",
                    "status": "pass",
                    "message": f"Python {version} meets requirement (≥ {required_major}.{required_minor})",
                    "details": {
                        "version": version,
                        "required": f"{required_major}.{required_minor}",
                    },
                }
            else:
                return {
                    "check": "python_version",
                    "status": "fail",
                    "message": f"Python {version} is below required version {required_major}.{required_minor}",
                    "details": {
                        "version": version,
                        "required": f"{required_major}.{required_minor}",
                    },
                }

        except FileNotFoundError:
            return {
                "check": "python_version",
                "status": "fail",
                "message": "Python not found in PATH",
                "details": {"error": "python3 command not found"},
            }
        except Exception as e:
            return {
                "check": "python_version",
                "status": "fail",
                "message": f"Error checking Python version: {str(e)}",
                "details": {"error": str(e)},
            }

    def check_nodejs_version(self) -> ValidationResult:
        """
        Check Node.js version (≥ 20).

        Returns:
            ValidationResult for Node.js version check
        """
        required_major = 20

        try:
            result = subprocess.run(
                ["node", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                return {
                    "check": "nodejs_version",
                    "status": "fail",
                    "message": f"Failed to check Node.js version: {result.stderr}",
                    "details": {"error": result.stderr},
                }

            # Parse version from output like "v20.10.0"
            version_str = result.stdout.strip()
            if version_str.startswith("v"):
                version_str = version_str[1:]

            version_numbers = version_str.split(".")
            if len(version_numbers) < 1:
                return {
                    "check": "nodejs_version",
                    "status": "fail",
                    "message": f"Invalid Node.js version format: {version_str}",
                    "details": {"version": version_str},
                }

            major = int(version_numbers[0])

            if major >= required_major:
                return {
                    "check": "nodejs_version",
                    "status": "pass",
                    "message": f"Node.js {version_str} meets requirement (≥ {required_major})",
                    "details": {
                        "version": version_str,
                        "required": str(required_major),
                    },
                }
            else:
                return {
                    "check": "nodejs_version",
                    "status": "fail",
                    "message": f"Node.js {version_str} is below required version {required_major}",
                    "details": {
                        "version": version_str,
                        "required": str(required_major),
                    },
                }

        except FileNotFoundError:
            return {
                "check": "nodejs_version",
                "status": "fail",
                "message": "Node.js not found in PATH",
                "details": {"error": "node command not found"},
            }
        except Exception as e:
            return {
                "check": "nodejs_version",
                "status": "fail",
                "message": f"Error checking Node.js version: {str(e)}",
                "details": {"error": str(e)},
            }

    def check_disk_space(self) -> ValidationResult:
        """
        Check disk space (≥ 10 GB free).

        Returns:
            ValidationResult for disk space check
        """
        required_gb = 10
        warn_threshold_gb = 5

        try:
            # Check disk space for current directory
            disk = psutil.disk_usage("/")
            free_gb = disk.free / (1024**3)

            if free_gb >= required_gb:
                return {
                    "check": "disk_space",
                    "status": "pass",
                    "message": f"Disk space sufficient: {free_gb:.1f} GB free",
                    "details": {
                        "free_gb": int(free_gb),
                        "required_gb": required_gb,
                    },
                }
            elif free_gb >= warn_threshold_gb:
                return {
                    "check": "disk_space",
                    "status": "warn",
                    "message": f"Disk space low: {free_gb:.1f} GB free (recommended: {required_gb} GB)",
                    "details": {
                        "free_gb": int(free_gb),
                        "required_gb": required_gb,
                    },
                }
            else:
                return {
                    "check": "disk_space",
                    "status": "fail",
                    "message": f"Insufficient disk space: {free_gb:.1f} GB free (minimum: {warn_threshold_gb} GB)",
                    "details": {
                        "free_gb": int(free_gb),
                        "required_gb": required_gb,
                    },
                }

        except Exception as e:
            return {
                "check": "disk_space",
                "status": "fail",
                "message": f"Error checking disk space: {str(e)}",
                "details": {"error": str(e)},
            }

    def check_memory(self) -> ValidationResult:
        """
        Check available memory (≥ 4 GB).

        Returns:
            ValidationResult for memory check
        """
        required_gb = 4
        warn_threshold_gb = 2

        try:
            memory = psutil.virtual_memory()
            available_gb = memory.available / (1024**3)

            if available_gb >= required_gb:
                return {
                    "check": "memory",
                    "status": "pass",
                    "message": f"Memory sufficient: {available_gb:.1f} GB available",
                    "details": {
                        "available_gb": int(available_gb),
                        "required_gb": required_gb,
                    },
                }
            elif available_gb >= warn_threshold_gb:
                return {
                    "check": "memory",
                    "status": "warn",
                    "message": f"Memory low: {available_gb:.1f} GB available (recommended: {required_gb} GB)",
                    "details": {
                        "available_gb": int(available_gb),
                        "required_gb": required_gb,
                    },
                }
            else:
                return {
                    "check": "memory",
                    "status": "fail",
                    "message": f"Insufficient memory: {available_gb:.1f} GB available (minimum: {warn_threshold_gb} GB)",
                    "details": {
                        "available_gb": int(available_gb),
                        "required_gb": required_gb,
                    },
                }

        except Exception as e:
            return {
                "check": "memory",
                "status": "fail",
                "message": f"Error checking memory: {str(e)}",
                "details": {"error": str(e)},
            }

    def validate_all_config(self) -> list[ValidationResult]:
        """
        Run all configuration validation checks.

        Returns:
            List of validation results for all config checks
        """
        results: list[ValidationResult] = []

        results.extend(self.check_required_secrets())
        results.append(self.validate_database_connectivity())
        results.append(self.check_api_base_url_accessibility())
        results.append(self.validate_cors_configuration())
        results.extend(self.test_model_provider_api_keys())

        return results

    def check_required_secrets(self) -> list[ValidationResult]:
        """
        Check required secrets (JWT_SECRET, ENCRYPTION_KEY).

        Returns:
            List of validation results for JWT_SECRET and ENCRYPTION_KEY
        """
        results: list[ValidationResult] = []

        # Check AUTH_JWT_SECRET
        jwt_secret = self.settings.auth_jwt_secret.strip()
        if not jwt_secret:
            results.append({
                "check": "jwt_secret",
                "status": "fail",
                "message": "AUTH_JWT_SECRET is not set",
                "details": {
                    "required": True,
                    "current_value": "",
                    "hint": "Generate with: openssl rand -hex 32",
                },
            })
        elif jwt_secret == AUTH_JWT_SECRET_PLACEHOLDER:
            results.append({
                "check": "jwt_secret",
                "status": "fail",
                "message": "AUTH_JWT_SECRET uses example placeholder",
                "details": {
                    "required": True,
                    "current_value": "placeholder",
                    "hint": "Generate with: openssl rand -hex 32",
                },
            })
        elif len(jwt_secret) < 32:
            results.append({
                "check": "jwt_secret",
                "status": "fail",
                "message": f"AUTH_JWT_SECRET too short (length: {len(jwt_secret)}, minimum: 32)",
                "details": {
                    "required": True,
                    "current_length": len(jwt_secret),
                    "minimum_length": 32,
                    "hint": "Generate with: openssl rand -hex 32",
                },
            })
        else:
            results.append({
                "check": "jwt_secret",
                "status": "pass",
                "message": "AUTH_JWT_SECRET is properly configured",
                "details": {"length": len(jwt_secret)},
            })

        # Check HARNESS_SECRET_ENCRYPTION_KEY
        encryption_key = self.settings.harness_secret_encryption_key.strip()
        is_production = self.settings.app_env.strip().lower() == "production"

        if not encryption_key:
            results.append({
                "check": "encryption_key",
                "status": "fail" if is_production else "warn",
                "message": (
                    "HARNESS_SECRET_ENCRYPTION_KEY is not set"
                    if is_production
                    else "HARNESS_SECRET_ENCRYPTION_KEY is not set (required in production)"
                ),
                "details": {
                    "required": is_production,
                    "current_value": "",
                    "hint": "Generate with: python3 scripts/generate-runtime-secrets.py",
                },
            })
        elif encryption_key == HARNESS_SECRET_ENCRYPTION_KEY_PLACEHOLDER:
            results.append({
                "check": "encryption_key",
                "status": "fail" if is_production else "warn",
                "message": (
                    "HARNESS_SECRET_ENCRYPTION_KEY uses example placeholder"
                    if is_production
                    else "HARNESS_SECRET_ENCRYPTION_KEY uses example placeholder (replace before production)"
                ),
                "details": {
                    "required": is_production,
                    "current_value": "placeholder",
                    "hint": "Generate with: python3 scripts/generate-runtime-secrets.py",
                },
            })
        elif len(encryption_key) < 32:
            results.append({
                "check": "encryption_key",
                "status": "fail" if is_production else "warn",
                "message": f"HARNESS_SECRET_ENCRYPTION_KEY too short (length: {len(encryption_key)}, minimum: 32)",
                "details": {
                    "required": is_production,
                    "current_length": len(encryption_key),
                    "minimum_length": 32,
                    "hint": "Generate with: python3 scripts/generate-runtime-secrets.py",
                },
            })
        else:
            results.append({
                "check": "encryption_key",
                "status": "pass",
                "message": "HARNESS_SECRET_ENCRYPTION_KEY is properly configured",
                "details": {"length": len(encryption_key)},
            })

        return results

    def validate_database_connectivity(self) -> ValidationResult:
        """
        Validate database connectivity.

        Returns:
            ValidationResult for database connectivity check
        """
        try:
            # Execute a simple query to test connectivity
            result = self.session.execute(text("SELECT 1"))
            result.fetchone()

            return {
                "check": "database_connectivity",
                "status": "pass",
                "message": "Database connection is healthy",
                "details": {"database_url": self._mask_db_credentials(self.settings.database_url)},
            }
        except Exception as e:
            return {
                "check": "database_connectivity",
                "status": "fail",
                "message": f"Database connection failed: {str(e)}",
                "details": {
                    "database_url": self._mask_db_credentials(self.settings.database_url),
                    "error": str(e),
                },
            }

    def check_api_base_url_accessibility(self) -> ValidationResult:
        """
        Check API_BASE_URL accessibility.

        Returns:
            ValidationResult for API_BASE_URL accessibility check
        """
        api_base_url = str(self.settings.api_base_url)

        try:
            # Attempt to reach the health endpoint or root
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{api_base_url}/health", follow_redirects=True)

                if response.status_code == 200:
                    return {
                        "check": "api_base_url",
                        "status": "pass",
                        "message": f"API_BASE_URL is accessible: {api_base_url}",
                        "details": {
                            "url": api_base_url,
                            "status_code": response.status_code,
                        },
                    }
                else:
                    return {
                        "check": "api_base_url",
                        "status": "warn",
                        "message": f"API_BASE_URL returned non-200 status: {response.status_code}",
                        "details": {
                            "url": api_base_url,
                            "status_code": response.status_code,
                        },
                    }
        except httpx.ConnectError as e:
            return {
                "check": "api_base_url",
                "status": "warn",
                "message": f"Cannot connect to API_BASE_URL (may not be started yet): {api_base_url}",
                "details": {
                    "url": api_base_url,
                    "error": str(e),
                },
            }
        except Exception as e:
            return {
                "check": "api_base_url",
                "status": "fail",
                "message": f"API_BASE_URL check failed: {str(e)}",
                "details": {
                    "url": api_base_url,
                    "error": str(e),
                },
            }

    def validate_cors_configuration(self) -> ValidationResult:
        """
        Validate CORS configuration.

        Returns:
            ValidationResult for CORS configuration check
        """
        app_env = self.settings.app_env.strip().lower()
        console_url = str(self.settings.console_base_url)
        app_url = str(self.settings.app_base_url)

        # CORS is permissive in development/test, restrictive in production
        if app_env in {"development", "test"}:
            return {
                "check": "cors_configuration",
                "status": "pass",
                "message": "CORS is configured for development environment",
                "details": {
                    "environment": app_env,
                    "mode": "permissive",
                    "console_url": console_url,
                    "app_url": app_url,
                },
            }
        else:
            # In production, verify URLs are not localhost
            if "localhost" in console_url or "127.0.0.1" in console_url:
                return {
                    "check": "cors_configuration",
                    "status": "warn",
                    "message": "CONSOLE_BASE_URL uses localhost in production environment",
                    "details": {
                        "environment": app_env,
                        "console_url": console_url,
                        "recommendation": "Set CONSOLE_BASE_URL to production domain",
                    },
                }
            elif "localhost" in app_url or "127.0.0.1" in app_url:
                return {
                    "check": "cors_configuration",
                    "status": "warn",
                    "message": "APP_BASE_URL uses localhost in production environment",
                    "details": {
                        "environment": app_env,
                        "app_url": app_url,
                        "recommendation": "Set APP_BASE_URL to production domain",
                    },
                }
            else:
                return {
                    "check": "cors_configuration",
                    "status": "pass",
                    "message": "CORS is properly configured for production",
                    "details": {
                        "environment": app_env,
                        "mode": "restrictive",
                        "console_url": console_url,
                        "app_url": app_url,
                    },
                }

    def test_model_provider_api_keys(self) -> list[ValidationResult]:
        """
        Test model provider API keys (optional).

        Returns:
            List of validation results for model provider API keys
        """
        results: list[ValidationResult] = []

        # Check DEEPSEEK_API_KEY (optional)
        deepseek_key = self.settings.deepseek_api_key.strip()
        if not deepseek_key:
            results.append({
                "check": "deepseek_api_key",
                "status": "warn",
                "message": "DEEPSEEK_API_KEY not configured (optional)",
                "details": {
                    "required": False,
                    "provider": "DeepSeek",
                },
            })
        else:
            # Basic validation: key should have reasonable length
            if len(deepseek_key) < 20:
                results.append({
                    "check": "deepseek_api_key",
                    "status": "warn",
                    "message": f"DEEPSEEK_API_KEY seems too short (length: {len(deepseek_key)})",
                    "details": {
                        "required": False,
                        "provider": "DeepSeek",
                        "key_length": len(deepseek_key),
                    },
                })
            else:
                results.append({
                    "check": "deepseek_api_key",
                    "status": "pass",
                    "message": "DEEPSEEK_API_KEY is configured",
                    "details": {
                        "required": False,
                        "provider": "DeepSeek",
                        "key_length": len(deepseek_key),
                    },
                })

        # Check MODEL_GATEWAY_API_KEY
        gateway_key = self.settings.model_gateway_api_key.strip()
        if not gateway_key or gateway_key == "replace-me":
            results.append({
                "check": "model_gateway_api_key",
                "status": "warn",
                "message": "MODEL_GATEWAY_API_KEY not configured or uses placeholder",
                "details": {
                    "required": False,
                    "provider": "Model Gateway",
                    "hint": "Set MODEL_GATEWAY_API_KEY if using model gateway",
                },
            })
        else:
            results.append({
                "check": "model_gateway_api_key",
                "status": "pass",
                "message": "MODEL_GATEWAY_API_KEY is configured",
                "details": {
                    "required": False,
                    "provider": "Model Gateway",
                    "key_length": len(gateway_key),
                },
            })

        return results

    def _mask_db_credentials(self, database_url: str) -> str:
        """
        Mask database credentials in URL for logging.

        Args:
            database_url: Database connection URL

        Returns:
            Masked database URL
        """
        if "@" not in database_url:
            return database_url

        # Split by @ to separate credentials from host
        parts = database_url.split("@")
        if len(parts) != 2:
            return database_url

        # Mask the credentials part
        protocol_and_creds = parts[0]
        host_and_db = parts[1]

        # Extract protocol
        if "://" in protocol_and_creds:
            protocol, creds = protocol_and_creds.split("://", 1)
            return f"{protocol}://***:***@{host_and_db}"

        return f"***:***@{host_and_db}"
