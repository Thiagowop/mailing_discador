"""Cliente de autenticação para API 3C Plus.

Este módulo fornece a classe :class:`ThreeCAuthClient` responsável por
realizar autenticação na API 3C Plus, mantendo o token em memória e
oferecendo helpers para verificar sessão e realizar logout.
"""

from __future__ import annotations

import logging
import os
import random
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests  # type: ignore[import-untyped]
from dotenv import load_dotenv
from requests import Response, Session  # type: ignore[import-untyped]
from requests.exceptions import RequestException, Timeout  # type: ignore[import-untyped]


# ---------------------------------------------------------------------------
# Exceções
# ---------------------------------------------------------------------------


class ThreeCAuthError(Exception):
    """Erro base para autenticação na API 3C Plus."""


class InvalidCredentials(ThreeCAuthError):
    """Credenciais inválidas fornecidas."""


class Unauthorized(ThreeCAuthError):
    """Requisição sem autorização."""


class TokenExpired(Unauthorized):
    """Token expirado ou inválido."""


class ApiUnavailable(ThreeCAuthError):
    """API indisponível temporariamente."""


class RateLimitExceeded(ThreeCAuthError):
    """Limite de requisições excedido."""


class InputInvalid(ThreeCAuthError):
    """Dados de entrada inválidos."""


# ---------------------------------------------------------------------------
# Estruturas auxiliares
# ---------------------------------------------------------------------------


@dataclass
class Credentials:
    """Credenciais necessárias para autenticação."""

    user: str
    password: str
    company_id: int
    company_domain: str


# ---------------------------------------------------------------------------
# Cliente principal
# ---------------------------------------------------------------------------


class ThreeCAuthClient:
    """Cliente responsável por autenticação na API 3C Plus."""


    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float = 15.0,
        max_retries: int = 3,
        session: Optional[Session] = None,
    ) -> None:
        # Carregar variáveis do ambiente (.env)
        load_dotenv()
        raw_base = base_url or os.getenv("THREECPLUS_BASE_URL")
        if not raw_base:
            # Fail-Fast: sem fallback de URL
            raise InputInvalid(
                "BASE_URL ausente: defina THREECPLUS_BASE_URL no .env ou passe base_url no construtor"
            )
        raw_base = raw_base.rstrip("/")
        # Garantir sufixo /api/v1
        self.base_url = raw_base if raw_base.endswith("/api/v1") else f"{raw_base}/api/v1"
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = session or requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        # Token: usar do ambiente apenas se nenhum base_url explícito foi passado
        self._token: Optional[str] = None
        if base_url is None:
            token_env = os.getenv("THREECPLUS_API_TOKEN")
            if token_env:
                self._token = token_env
                self.session.headers.update({"Authorization": f"Bearer {token_env}"})
        self.logger = logging.getLogger(self.__class__.__name__)

    # ------------------------------------------------------------------
    # Utilidades internas
    # ------------------------------------------------------------------
    def _get_credentials(
        self,
        user: str | None,
        password: str | None,
        company_id: int | None,
        company_domain: str | None,
    ) -> Credentials:
        """Obtém credenciais a partir de argumentos ou variáveis de ambiente."""

        env = os.environ
        # Preferir padrão THREECPLUS_*; manter compatibilidade leve com THREEC_*
        u = user or env.get("THREECPLUS_USERNAME") or env.get("THREEC_USER")
        p = password or env.get("THREECPLUS_PASSWORD") or env.get("THREEC_PASSWORD")
        cid_raw = (
            company_id if company_id is not None else env.get("THREECPLUS_COMPANY_ID") or env.get("THREEC_COMPANY_ID")
        )
        domain = company_domain or env.get("THREECPLUS_COMPANY_DOMAIN") or env.get("THREEC_COMPANY_DOMAIN")

        cid_int: Optional[int]
        try:
            cid_int = int(cid_raw) if cid_raw is not None else None
        except (TypeError, ValueError):
            cid_int = None

        # Credenciais mínimas: username/password. company_id/domain são opcionais por tenant.
        if not (u and p):
            raise InputInvalid(
                "Credenciais incompletas (username/password). Defina no .env ou passe por parâmetro."
            )

        # Se não houver company_id/domain, usar valores neutros (0 e "")
        return Credentials(u, p, cid_int or 0, domain or "")

    def _extract_token(self, data: Dict[str, Any]) -> Optional[str]:
        """Extrai o token da resposta de autenticação."""

        for key in ("api_token", "token"):
            if key in data and isinstance(data[key], str):
                return data[key]

        if isinstance(data.get("data"), dict):
            return self._extract_token(data["data"])  # type: ignore[arg-type]
        return None

    def _error_message(self, response: Response) -> str:
        try:
            data = response.json()
            return (
                data.get("message")
                or data.get("error")
                or response.text
            )
        except ValueError:
            return response.text

    # ------------------------------------------------------------------
    # Métodos públicos
    # ------------------------------------------------------------------
    def login(
        self,
        user: str | None = None,
        password: str | None = None,
        company_id: int | None = None,
        company_domain: str | None = None,
    ) -> str:
        """Realiza login e armazena o token em memória."""

        # Se houver token pré-carregado do ambiente e não foram passadas credenciais, não relogar
        if self._token and not (user or password):
            self.logger.info("Login ignorado: token presente em ambiente")
            return self._token

        creds = self._get_credentials(user, password, company_id, company_domain)
        url = f"{self.base_url}/authenticate"
        # Tenants variam: maioria aceita {username,password}; manter compatibilidade com {user,company_*}
        payload = {
            "username": creds.user,
            "password": creds.password,
        }
        # Se houver dados de company, enviar também
        if creds.company_id:
            payload["company_id"] = creds.company_id
        if creds.company_domain:
            payload["company_domain"] = creds.company_domain

        last_exc: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.post(
                    url, json=payload, timeout=self.timeout
                )
            except Timeout as exc:  # transient
                self.logger.warning(
                    "Timeout ao autenticar (tentativa %s)", attempt
                )
                last_exc = exc
            except RequestException as exc:  # other network errors
                self.logger.warning("Erro de rede: %s", exc)
                last_exc = exc
            else:
                if response.status_code >= 500:
                    self.logger.warning(
                        "Erro %s na API (tentativa %s)",
                        response.status_code,
                        attempt,
                    )
                    last_exc = ApiUnavailable(
                        f"Erro {response.status_code} na API"
                    )
                else:
                    break

            if attempt < self.max_retries:
                sleep = (2 ** (attempt - 1)) + random.uniform(0, 0.1)
                time.sleep(sleep)
        else:
            raise ApiUnavailable("Serviço indisponível, tente novamente mais tarde.") from last_exc

        return self._handle_login_response(response)

    def _handle_login_response(self, response: Response) -> str:
        if response.status_code == 200:
            token = self._extract_token(response.json())
            if not token:
                raise ThreeCAuthError(
                    "Token não encontrado na resposta de autenticação."
                )
            self._token = token
            self.session.headers.update({"Authorization": f"Bearer {token}"})
            self.logger.info("Autenticação realizada com sucesso.")
            return token

        if response.status_code in {400, 422}:
            raise InputInvalid(self._error_message(response))
        if response.status_code == 401:
            raise InvalidCredentials("Credenciais inválidas.")
        if response.status_code == 429:
            raise RateLimitExceeded(
                "Muitas requisições. Aguarde alguns instantes antes de tentar novamente."
            )
        if response.status_code >= 500:
            raise ApiUnavailable("Serviço indisponível, tente novamente mais tarde.")

        raise ThreeCAuthError(
            f"Erro inesperado ao autenticar: {response.status_code}"
        )

    def verificar_sessao(self) -> Dict[str, Any]:
        """Verifica se a sessão é válida retornando dados do usuário."""
        if not self._token:
            raise Unauthorized("Usuário não autenticado.")

        url = f"{self.base_url}/me"
        response = self.session.get(url, timeout=self.timeout)

        if response.status_code == 200:
            return response.json()
        if response.status_code == 401:
            raise TokenExpired("Token expirado ou inválido.")
        if response.status_code == 403:
            raise Unauthorized("Acesso negado.")
        if response.status_code == 429:
            raise RateLimitExceeded(
                "Muitas requisições. Aguarde alguns instantes antes de tentar novamente."
            )
        if response.status_code >= 500:
            raise ApiUnavailable("Serviço indisponível, tente novamente mais tarde.")

        raise ThreeCAuthError(
            f"Erro inesperado ao verificar sessão: {response.status_code}"
        )

    def logout(self) -> None:
        """Realiza logout e limpa o token armazenado."""
        if not self._token:
            raise Unauthorized("Usuário não autenticado.")

        url = f"{self.base_url}/logout"
        response = self.session.get(url, timeout=self.timeout)

        if response.status_code == 200:
            self.logger.info("Logout realizado com sucesso.")
            self._token = None
            self.session.headers.pop("Authorization", None)
            return
        if response.status_code in {401, 403}:
            self._token = None
            self.session.headers.pop("Authorization", None)
            raise TokenExpired("Sessão expirada.")
        if response.status_code == 429:
            raise RateLimitExceeded(
                "Muitas requisições. Aguarde alguns instantes antes de tentar novamente."
            )
        if response.status_code >= 500:
            raise ApiUnavailable("Serviço indisponível, tente novamente mais tarde.")

        raise ThreeCAuthError(
            f"Erro inesperado ao realizar logout: {response.status_code}"
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def auth_headers(self) -> Dict[str, str]:
        """Retorna headers de autenticação."""
        if not self._token:
            raise Unauthorized("Usuário não autenticado.")
        return {"Authorization": f"Bearer {self._token}"}

    @property
    def is_autenticado(self) -> bool:
        """Indica se há token armazenado."""
        return self._token is not None
