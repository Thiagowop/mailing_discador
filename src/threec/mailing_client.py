# -*- coding: utf-8 -*-
"""Cliente para operações de mailing na API 3C Plus.

O módulo implementa a classe :class:`ThreeCMailingClient` responsável por
criar containers de mailing, enviar contatos e ajustar peso do mailing.
Ele reutiliza o cliente de autenticação :class:`threec.auth.ThreeCAuthClient`
para manter o token válido e realizar as requisições autenticadas.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional

import requests  # type: ignore[import-untyped]
from requests import Response, Session  # type: ignore[import-untyped]
from requests.exceptions import RequestException, Timeout  # type: ignore[import-untyped]

from .auth import (
    ApiUnavailable,
    InputInvalid,
    RateLimitExceeded,
    ThreeCAuthClient,
    Unauthorized,
)
from dotenv import load_dotenv
from ..utils.extracao_bases import carregar_contatos_csv_semicolon
from datetime import datetime
import csv
import io
 


# ---------------------------------------------------------------------------
# Exceções específicas
# ---------------------------------------------------------------------------


class ThreeCMailingError(Exception):
    """Erro base para operações de mailing."""


class CampaignNotFound(ThreeCMailingError):
    """Campanha não encontrada."""


class CreateMailingFailed(ThreeCMailingError):
    """Falha ao criar container de mailing."""


class UploadFailed(ThreeCMailingError):
    """Falha ao enviar contatos."""


class WeightUpdateFailed(ThreeCMailingError):
    """Falha ao atualizar peso do mailing."""


# ---------------------------------------------------------------------------
# Estruturas de dados
# ---------------------------------------------------------------------------


@dataclass
class Contact:
    """Representa um contato a ser enviado para a API."""

    name: Optional[str] = None
    document: Optional[str] = None
    phones: List[str] = field(default_factory=list)
    email: Optional[str] = None
    external_id: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:  # validações simples
        if len(self.phones) > 20:
            raise ValueError("Cada contato pode conter no máximo 20 telefones")
        self.phones = [str(p) for p in self.phones]

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "name": self.name,
            "document": self.document,
            "phones": self.phones,
            "email": self.email,
            "external_id": self.external_id,
        }
        data.update(self.extra)
        # Remove chaves com valor None
        return {k: v for k, v in data.items() if v is not None}


# ---------------------------------------------------------------------------
# Cliente principal
# ---------------------------------------------------------------------------


class ThreeCMailingClient:
    """Cliente desacoplado para operações de mailing na 3C Plus."""

    DEFAULT_ENDPOINTS: Dict[str, List[str]] = {
        # tente com e sem /api/v1 (tenants variam)
        "listar_campanhas": [
            "api/v1/campaigns",
            "campaigns",
            "api/v1/agent/campaigns",
            "agent/campaigns",
        ],
        # upload CSV 1-passo (cria lista + importa)
        "enviar_csv": [
            "api/v1/campaigns/{campaign_id}/lists/csv",
            "campaigns/{campaign_id}/lists/csv",
            # variações com agente (alguns tenants expõem via /agent)
            "api/v1/agent/campaigns/{campaign_id}/lists/csv",
            "agent/campaigns/{campaign_id}/lists/csv",
            # fallbacks legado
            "api/v1/mailing/list/{mailing_id}/csv",
            "mailing/list/{mailing_id}/csv",
            "api/v1/mailing/list/csv",
            "mailing/list/csv",
        ],
        # ajuste de peso/ativação da lista
        "ajustar_peso": [
            # alguns tenants usam /weight, outros /updateWeight
            "api/v1/campaigns/{campaign_id}/lists/{list_id}/weight",
            "campaigns/{campaign_id}/lists/{list_id}/weight",
            "api/v1/campaigns/{campaign_id}/lists/{list_id}/updateWeight",
            "campaigns/{campaign_id}/lists/{list_id}/updateWeight",
            # fallback antigo (alguns tenants): 
            "api/v1/mailings/{mailing_id}/weight",
            "mailings/{mailing_id}/weight",
        ],
        # listar listas de uma campanha (para validação pós-upload)
        "listar_listas": [
            "api/v1/campaigns/{campaign_id}/lists",
            "campaigns/{campaign_id}/lists",
            "api/v1/agent/campaigns/{campaign_id}/lists",
            "agent/campaigns/{campaign_id}/lists",
        ],
        # exclusão de lista (quando suportado pelo tenant)
        "deletar_lista": [
            # padrão por campanha/lista
            "api/v1/campaigns/{campaign_id}/lists/{list_id}",
            "campaigns/{campaign_id}/lists/{list_id}",
            # fallback legado por mailing_id
            "api/v1/mailings/{mailing_id}",
            "mailings/{mailing_id}",
        ],
    }

    def __init__(
        self,
        auth_client: ThreeCAuthClient,
        *,
        base_url: str | None = None,
        timeout: float = 20.0,
        max_retries: int = 3,
        endpoints: Optional[Dict[str, Iterable[str]]] = None,
        session: Optional[Session] = None,
        persist_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        self.auth_client = auth_client
        self.base_url = (base_url or auth_client.base_url).rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = session or auth_client.session or requests.Session()
        # Logger
        LOG_DIR = os.getenv("LOG_DIR", "logs")
        os.makedirs(LOG_DIR, exist_ok=True)
        LOG_LEVEL = str(os.getenv("LOG_LEVEL", "INFO")).upper()
        self.logger = logging.getLogger(self.__class__.__name__)
        if not self.logger.handlers:
            self.logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
            fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
            fh = logging.FileHandler(os.path.join(LOG_DIR, "3cplus.log"), encoding="utf-8")
            fh.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
            fh.setFormatter(fmt)
            eh = logging.FileHandler(os.path.join(LOG_DIR, "error.log"), encoding="utf-8")
            eh.setLevel(logging.ERROR)
            eh.setFormatter(fmt)
            ch = logging.StreamHandler()
            ch.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
            ch.setFormatter(fmt)
            self.logger.addHandler(fh)
            self.logger.addHandler(eh)
            self.logger.addHandler(ch)
        # merge endpoints: defaults + overrides
        self.endpoints: Dict[str, List[str]] = {k: list(v) for k, v in self.DEFAULT_ENDPOINTS.items()}
        if endpoints:
            for k, v in endpoints.items():
                self.endpoints[k] = list(v)
        self.persist_callback = persist_callback
        self.mailing_ids: List[int] = []
        self.campaign_ids: List[int] = []

    # ------------------------------------------------------------------
    # Resolução de endpoints
    # ------------------------------------------------------------------
    def _resolve_endpoint(self, key: str) -> List[str]:
        paths = self.endpoints.get(key)
        if not paths:
            raise ThreeCMailingError(f"Endpoint não configurado para: {key}")
        base_has_v1 = self.base_url.rstrip("/").endswith("/api/v1")
        clean: List[str] = []
        for p in paths:
            p2 = p.lstrip("/")
            if base_has_v1 and p2.startswith("api/v1/"):
                p2 = p2[len("api/v1/") :]
            clean.append(p2)
        return clean

    # ------------------------------------------------------------------
    # Requisições HTTP com retry e variações de endpoints
    # ------------------------------------------------------------------
    def _request_json(
        self,
        method: str,
        endpoint_key: str,
        *,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        data_fields: Optional[Dict[str, Any]] = None,
        files: Any | None = None,
        idempotent: bool = False,
    ) -> Response:
        paths = self._resolve_endpoint(endpoint_key)
        last_exc: Exception | None = None
        for path in paths:
            url = f"{self.base_url}/{path}".replace(" ", "/")
            headers: Dict[str, str] = {}
            if idempotent:
                headers["Idempotency-Key"] = str(uuid.uuid4())
            for attempt in range(1, self.max_retries + 1):
                try:
                    response = self.session.request(
                        method,
                        url,
                        json=json_data,
                        params=params,
                        data=data_fields,
                        files=files,
                        headers=headers or None,
                        timeout=self.timeout,
                    )
                except Timeout as exc:
                    last_exc = exc
                except RequestException as exc:
                    last_exc = exc
                else:
                    if response.status_code == 404:
                        # tenta próxima variação
                        break
                    if response.status_code >= 500:
                        last_exc = ApiUnavailable(
                            f"Erro {response.status_code} na API"
                        )
                    else:
                        return response
                if attempt < self.max_retries:
                    sleep = (2 ** (attempt - 1)) + 0.1
                    time.sleep(sleep)
            if last_exc and isinstance(last_exc, ApiUnavailable):
                continue
        # se chegou aqui, algo deu errado
        if isinstance(last_exc, Timeout):
            raise ApiUnavailable("Tempo de requisição excedido") from last_exc
        if isinstance(last_exc, RequestException):
            raise ApiUnavailable("Erro de rede") from last_exc
        # pode ter retornado 404 em todos os caminhos
        raise CampaignNotFound(f"Endpoint {endpoint_key} não encontrado")

    def _get_json(self, endpoint_key: str, *, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        resp = self._request_json("GET", endpoint_key, params=params)
        return self._handle_response(resp, endpoint_key)

    def _post_json(
        self,
        endpoint_key: str,
        json_data: Dict[str, Any] | None = None,
        data_fields: Dict[str, Any] | None = None,
        files: Any | None = None,
    ) -> Dict[str, Any]:
        resp = self._request_json(
            "POST",
            endpoint_key,
            json_data=json_data,
            data_fields=data_fields,
            files=files,
            idempotent=True,
        )
        return self._handle_response(resp, endpoint_key)

    def _put_json(self, endpoint_key: str, json_data: Dict[str, Any]) -> Dict[str, Any]:
        resp = self._request_json(
            "PUT", endpoint_key, json_data=json_data, idempotent=True
        )
        return self._handle_response(resp, endpoint_key)

    def _handle_response(self, response: Response, endpoint_key: str) -> Dict[str, Any]:
        if response.status_code in {200, 201, 202, 204}:
            if response.status_code == 204:
                return {}
            try:
                return response.json()
            except ValueError as exc:
                raise ThreeCMailingError("Resposta inválida da API") from exc
        if response.status_code in {400, 422}:
            msg = "Payload inválido"
            try:
                body = response.text.strip()
                if body:
                    msg = f"Payload inválido: {body[:200]}"
            except Exception:
                pass
            raise InputInvalid(msg)
        if response.status_code in {401, 403}:
            msg = "Não autorizado"
            try:
                body = response.text.strip()
                if body:
                    msg = f"Não autorizado: {body[:200]}"
            except Exception:
                pass
            raise Unauthorized(msg)
        if response.status_code == 404:
            raise CampaignNotFound(f"Endpoint {endpoint_key} não encontrado")
        if response.status_code == 409:
            raise UploadFailed("Dados duplicados")
        if response.status_code == 429:
            raise RateLimitExceeded("Muitas requisições")
        if response.status_code >= 500:
            raise ApiUnavailable("Serviço indisponível")
        raise ThreeCMailingError(f"Erro inesperado ({response.status_code}) ao acessar {endpoint_key}")

    # ------------------------------------------------------------------
    # Operações públicas
    # ------------------------------------------------------------------
    def listar_campanhas(
        self, filtro: str | None = None, somente_ativas: bool = True
    ) -> List[Dict[str, Any]]:
        pagina = 1
        result: List[Dict[str, Any]] = []
        vistos: set[int] = set()
        while True:
            data = self._get_json("listar_campanhas", params={"page": pagina})
            campanhas = data.get("data") or data.get("campaigns") or []
            for camp in campanhas:
                if filtro and filtro.lower() not in str(camp.get("name", "")).lower():
                    continue
                if somente_ativas and not camp.get("active", True):
                    continue
                cid = camp.get("id")
                if isinstance(cid, int):
                    if cid in vistos:
                        continue
                    vistos.add(cid)
                    self.campaign_ids.append(cid)
                result.append(camp)

            # Avalia pagina��o
            meta = data.get("meta")
            has_more = False
            if isinstance(meta, dict):
                pagination = meta.get("pagination") or meta
                if isinstance(pagination, dict):
                    current = pagination.get("current_page") or pagination.get("page")
                    total_pages = pagination.get("total_pages") or pagination.get("last_page")
                    try:
                        current_int = int(current) if current is not None else pagina
                    except (TypeError, ValueError):
                        current_int = pagina
                    try:
                        total_int = int(total_pages) if total_pages is not None else None
                    except (TypeError, ValueError):
                        total_int = None
                    if total_int is not None and current_int < total_int:
                        pagina = current_int + 1
                        has_more = True
                    else:
                        links = pagination.get("links")
                        if isinstance(links, dict) and links.get("next"):
                            pagina = current_int + 1
                            has_more = True
            # Fallback: se o lote retornado estiver vazio, encerra
            if not has_more or not campanhas:
                break
        return result

    # Fluxos apenas por CSV; funcionalidades de JSON foram removidas.

    def enviar_mailing_csv(
        self,
        mailing_id: int,
        caminho_csv: str,
        *,
        colmap: Dict[str, str] | None = None,
    ) -> Dict[str, Any]:
        """Fluxo legado de upload de CSV diretamente para um mailing existente."""
        if not os.path.exists(caminho_csv):
            raise UploadFailed("Arquivo CSV n�o encontrado")

        with open(caminho_csv, "rb") as fh:
            arquivo = (os.path.basename(caminho_csv), fh, "text/csv")
            candidatos = [p.lstrip("/") for p in self.endpoints.get("enviar_csv", [])]
            ultima_resposta: Response | None = None

            for caminho in candidatos:
                relativo = caminho.format(mailing_id=mailing_id)
                url = f"{self.base_url}/{relativo}".replace(" ", "/")
                headers = {"Idempotency-Key": str(uuid.uuid4())}
                usar_payload_id = "{mailing_id}" not in caminho
                data_form = {"mailing_id": str(mailing_id)} if usar_payload_id else None
                if colmap and data_form is not None:
                    data_form.update(colmap)

                try:
                    resp = self.session.request(
                        "POST",
                        url,
                        files={"file": arquivo},
                        data=data_form,
                        headers=headers,
                        timeout=self.timeout,
                    )
                    ultima_resposta = resp
                except Exception:
                    continue

                if resp.status_code == 404:
                    continue
                if resp.status_code in (200, 201):
                    return self._handle_response(resp, "enviar_csv")

            if ultima_resposta is not None:
                return self._handle_response(ultima_resposta, "enviar_csv")
            raise CampaignNotFound("Endpoint enviar_csv n�o encontrado")

    def criar_mailing_por_csv_em_campanha(
        self,
        campaign_id: int,
        caminho_csv: str,
        *,
        filename: Optional[str] = None,
        header: Optional[str] = None,
        colmap: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        1 passo: POST /campaigns/{campaign_id}/lists/csv (multipart)
        - file: CSV
        - header: string com a semântica das colunas na mesma ordem do CSV
          ex.: "identifier,name,document,areacodephone"
        Se 'colmap' for dado, mapeamos os nomes das colunas do CSV para a semântica.
        """
        if not os.path.exists(caminho_csv):
            raise UploadFailed("Arquivo CSV não encontrado")

        # Tentar gerar CSV sanitizado com colunas aceitas pela API
        # Saída: identifier,Nome,Cpf,areacodephone
        def _csv_sanitizado_bytes(path: str) -> Optional[bytes]:
            try:
                with open(path, "r", encoding="utf-8-sig") as fh:
                    linhas = fh.read().splitlines()
                if not linhas:
                    return None
                primeira = linhas[0]
                sep = ";" if ";" in primeira else ","
                cabecalho = [c.strip() for c in primeira.split(sep)]

                def _idx(nome: str) -> int:
                    try:
                        return cabecalho.index(nome)
                    except ValueError:
                        return -1

                i_cod = _idx("COD")
                i_nome = _idx("NOME / RAZAO SOCIAL")
                i_cpf = _idx("CPFCNPJ CLIENTE")
                i_phones = [_idx(f"TELEFONE_{i}") for i in range(1, 21)]
                i_phones = [i for i in i_phones if i >= 0]

                if i_cod < 0 or i_nome < 0 or i_cpf < 0 or not i_phones:
                    return None

                # Adequa ao formato aceito pelo endpoint CSV: identifier + areacodephone
                saida = ["identifier,areacodephone"]
                max_idx = max(i_cod, i_nome, i_cpf, max(i_phones))
                for linha in linhas[1:]:
                    if not linha.strip():
                        continue
                    partes = [p.strip() for p in linha.split(sep)]
                    if len(partes) <= max_idx:
                        continue
                    cod = partes[i_cod]
                    telefone = ""
                    for idx in i_phones:
                        val = partes[idx].strip()
                        if val:
                            telefone = val
                            break
                    if not telefone:
                        continue
                    # somente dígitos
                    telefone_digitos = "".join(ch for ch in telefone if ch.isdigit())
                    if not telefone_digitos:
                        continue
                    saida.append(f"{cod},{telefone_digitos}")
                if len(saida) == 1:
                    return None
                return ("\n".join(saida) + "\n").encode("utf-8")
            except Exception:
                return None


        # Preferir criação de container visível em UI via CSV
        candidates = [
            f"campaigns/{campaign_id}/lists/csv",
            f"agent/campaigns/{campaign_id}/lists/csv",
            # fallback: upload direto na campanha
            f"campaigns/{campaign_id}/mailing",
            f"agent/campaigns/{campaign_id}/mailing",
        ]

        sanitized = _csv_sanitizado_bytes(caminho_csv)
        last_resp: Response | None = None
        # tentar obter token para query param (Fluxoti exige api_token)
        api_token: Optional[str] = None
        try:
            auth_header = self.session.headers.get("Authorization") or ""
            if auth_header.lower().startswith("bearer "):
                api_token = auth_header.split(" ", 1)[1].strip()
        except Exception:
            api_token = None
        for path in candidates:
            url = f"{self.base_url}/{path}".replace(" ", "/")
            headers = {"Idempotency-Key": str(uuid.uuid4())}
            data = {"name": filename or os.path.basename(caminho_csv)}
            # parâmetros do formulário conforme documentação Fluxoti
            data.update({
                "delimiter": '"',
                "has_header": "1",
            })
            # definir separador e header[i]
            header_items: Dict[str, str] = {}
            separator_value = ","
            try:
                with open(caminho_csv, "r", encoding="utf-8-sig") as fh:
                    first_line = fh.readline()
                if ";" in first_line and "," not in first_line:
                    separator_value = ";"
                    cols = [c.strip() for c in first_line.split(";")]
                else:
                    separator_value = ","
                    cols = [c.strip() for c in first_line.split(",")]
                # Mapear cabeçalhos reais -> semântica (identifier, areacodephone, name, document, ...)
                for idx, col in enumerate(cols):
                    sem = (colmap or {}).get(col)
                    if sem:
                        header_items[f"header[{idx}]"] = sem
            except Exception:
                # se usamos CSV sanitizado, declarar cabeçalho conhecido
                if sanitized is not None:
                    cols = ["identifier", "areacodephone"]
                    separator_value = ","
                    for idx, col in enumerate(cols):
                        header_items[f"header[{idx}]"] = col
            if header_items:
                data.update(header_items)
            data["separator"] = separator_value
            try:
                self.logger.info(
                    "Upload CSV: tentando %s (sanitized=%s)",
                    url,
                    "sim" if sanitized is not None else "não",
                )
            except Exception:
                pass
            if sanitized is not None:
                # caminho com CSV sanitizado em memória
                files = {
                    ("mailing"): (
                        filename or os.path.basename(caminho_csv),
                        io.BytesIO(sanitized),
                        "text/csv",
                    )
                }
                try:
                    resp = self.session.request(
                        "POST", url, files=files, data=data, headers=headers, timeout=self.timeout,
                        params={"api_token": api_token} if api_token else None,
                    )
                except Timeout:
                    last_resp = None
                    continue
                except RequestException:
                    last_resp = None
                    continue
                else:
                    if resp.status_code in (200, 201, 202, 204):
                        if not resp.content:
                            return {"status": "ok"}
                        try:
                            return resp.json()
                        except ValueError:
                            return {"status": "ok"}
                    if resp.status_code == 404:
                        continue
                    try:
                        body_text = ""
                        try:
                            body_text = resp.text[:400]
                        except Exception:
                            body_text = ""
                        self.logger.info(
                            "Resposta CSV: status=%s, bytes=%s, body=%s",
                            resp.status_code,
                            len(resp.content or b""),
                            body_text,
                        )
                    except Exception:
                        pass
                    last_resp = resp
                    continue
            else:
                # caminho lendo arquivo CSV original
                try:
                    with open(caminho_csv, "rb") as f:
                        files = {"mailing": (filename or os.path.basename(caminho_csv), f, "text/csv")}
                        resp = self.session.request(
                            "POST", url, files=files, data=data, headers=headers, timeout=self.timeout,
                            params={"api_token": api_token} if api_token else None,
                        )
                except Timeout:
                    last_resp = None
                    continue
                except RequestException:
                    last_resp = None
                    continue
                else:
                    try:
                        body_text = ""
                        try:
                            body_text = resp.text[:400]
                        except Exception:
                            body_text = ""
                        self.logger.info(
                            "Resposta CSV: status=%s, bytes=%s, body=%s",
                            resp.status_code,
                            len(resp.content or b""),
                            body_text,
                        )
                    except Exception:
                        pass
                    if resp.status_code in (200, 201, 202, 204):
                        if not resp.content:
                            return {"status": "ok"}
                        try:
                            return resp.json()
                        except ValueError:
                            return {"status": "ok"}
                    if resp.status_code == 404:
                        continue
                    last_resp = resp
                    continue

            if last_resp is not None:
                return self._handle_response(last_resp, "enviar_csv")

        raise CampaignNotFound("Upload CSV por campanha não encontrado")

    def ajustar_peso_mailing(self, mailing_id: int, peso: int, *, campaign_id: Optional[int] = None) -> None:
        """
        PUT /campaigns/{campaign_id}/lists/{list_id}/weight   (preferencial)
        ou
        PUT /mailings/{mailing_id}/weight                     (fallback legado)
        """
        payload = {"weight": int(peso)}
        paths = self._resolve_endpoint("ajustar_peso")
        last: Response | None = None

        for path in paths:
            rel = path.format(
                campaign_id=campaign_id if campaign_id is not None else "",
                list_id=mailing_id,
                mailing_id=mailing_id,
            ).replace("//", "/").lstrip("/")
            url = f"{self.base_url}/{rel}"
            headers = {"Idempotency-Key": str(uuid.uuid4())}
            try:
                resp = self.session.request("PUT", url, json=payload, headers=headers, timeout=self.timeout)
            except (Timeout, RequestException):
                continue

            if resp.status_code in (200, 201, 202, 204):
                return
            if resp.status_code == 404:
                last = resp
                break
            last = resp

        if last is not None:
            self._handle_response(last, "ajustar_peso")
        raise WeightUpdateFailed("Falha ao atualizar peso (nenhuma variação de endpoint funcionou)")

    def listar_listas_da_campanha(self, campaign_id: int) -> Dict[str, Any]:
        """Obtém as listas (containers) visíveis da campanha, para validação.
        Tenta variações com e sem /api/v1 e com prefixo /agent.
        """
        candidates = [
            f"api/v1/campaigns/{campaign_id}/lists",
            f"campaigns/{campaign_id}/lists",
            f"api/v1/agent/campaigns/{campaign_id}/lists",
            f"agent/campaigns/{campaign_id}/lists",
        ]
        last: Response | None = None
        for path in candidates:
            url = f"{self.base_url}/{path}".replace(" ", "/")
            try:
                resp = self.session.request("GET", url, timeout=self.timeout)
            except (Timeout, RequestException):
                continue
            if resp.status_code in (200, 201, 202):
                return self._handle_response(resp, "listar_listas")
            if resp.status_code == 404:
                continue
            last = resp
        if last is not None:
            return self._handle_response(last, "listar_listas")
        raise CampaignNotFound("Falha ao obter listas da campanha")

    def deletar_lista_da_campanha(self, campaign_id: int, list_id: int) -> None:
        """Deleta a lista (container) quando o endpoint DELETE é suportado.
        Varia entre /campaigns/{id}/lists/{list_id} e /mailings/{mailing_id}.
        Fail-fast com erro claro quando nenhuma variação funciona.
        """
        paths = self._resolve_endpoint("deletar_lista")
        last: Response | None = None
        for path in paths:
            rel = path.format(
                campaign_id=campaign_id if campaign_id is not None else "",
                list_id=list_id,
                mailing_id=list_id,
            ).replace("//", "/").lstrip("/")
            url = f"{self.base_url}/{rel}"
            try:
                resp = self.session.request("DELETE", url, timeout=self.timeout)
            except (Timeout, RequestException) as exc:
                last = None
                continue
            if resp.status_code in (200, 202, 204):
                return
            if resp.status_code == 404:
                last = resp
                continue
            last = resp
        if last is not None:
            self._handle_response(last, "deletar_lista")
        raise ThreeCMailingError("Falha ao deletar lista: nenhuma variação de endpoint aceitou a requisição")

    def atualizar_lista_por_csv(
        self,
        campaign_id: int,
        list_id: int,
        csv_path: str,
        *,
        has_header: int = 1,
        delimiter: str = '"',
        sep: str = ';',
        ura_id: int | None = None,
    ) -> Dict[str, Any]:
        """Atualiza uma lista existente enviando CSV.
        Tenta variações conhecidas:
        - POST /mailing/list/{mailing_id}/csv (legado)
        - POST /campaigns/{id}/lists/{list_id}/csv (quando suportado)
        - POST /mailing/list/csv (legado exigindo mailing_id no form)
        Não há fallback por JSON neste cliente. Se todas falharem, retorna erro claro.
        """
        if not os.path.isfile(csv_path):
            raise InputInvalid(f"Arquivo CSV ausente: {csv_path}")

        candidates = [
            f"api/v1/mailing/list/{list_id}/csv",
            f"mailing/list/{list_id}/csv",
            f"api/v1/campaigns/{campaign_id}/lists/{list_id}/csv",
            f"campaigns/{campaign_id}/lists/{list_id}/csv",
            "api/v1/mailing/list/csv",
            "mailing/list/csv",
        ]

        data_fields: Dict[str, Any] = {
            "has_header": str(int(has_header)),
            "delimiter": delimiter,
            "separator": sep,
        }
        if ura_id is not None:
            data_fields["ura_id"] = str(int(ura_id))

        files = {"file": open(csv_path, "rb")}
        last: Response | None = None
        try:
            for path in candidates:
                rel = path.lstrip("/")
                url = f"{self.base_url}/{rel}"
                # alguns endpoints legados exigem mailing_id no corpo
                df = dict(data_fields)
                if rel.endswith("/list/csv"):
                    df["mailing_id"] = str(int(list_id))
                try:
                    resp = self.session.request(
                        "POST",
                        url,
                        files=files,
                        data=df,
                        timeout=self.timeout,
                    )
                except (Timeout, RequestException):
                    continue
                if resp.status_code in (200, 201, 202):
                    return self._handle_response(resp, "enviar_csv")
                if resp.status_code == 404:
                    continue
                last = resp
        finally:
            try:
                files["file"].close()
            except Exception:
                pass

        if last is not None:
            return self._handle_response(last, "enviar_csv")
        raise UploadFailed("Falha ao atualizar lista via CSV em todas as variações de endpoint")

    def inativar_todas_listas_da_campanha(self, campaign_id: int) -> int:
        """Define peso=0 para todas as listas visíveis da campanha.
        Útil para evitar uso de listas antigas quando a API não oferece DELETE.
        """
        try:
            resp = self.listar_listas_da_campanha(campaign_id)
        except Exception as e:
            self.logger.info("Listagem de listas falhou antes de inativação: %s", e)
            return 0
        itens: List[Dict[str, Any]] = []
        if isinstance(resp, dict):
            for key in ("data", "lists", "items"):
                val = resp.get(key)
                if isinstance(val, list):
                    itens = val
                    break
        count = 0
        for item in itens:
            list_id: Optional[int] = None
            for k in ("id", "list_id", "mailing_id"):
                v = item.get(k)
                if isinstance(v, int):
                    list_id = v
                    break
                if isinstance(v, str) and v.isdigit():
                    list_id = int(v)
                    break
            if list_id is None:
                # tentar chaves aninhadas comuns
                try:
                    list_id = self._extract_id(item, ["data.id", "data.list_id", "data.mailing_id"])
                except Exception:
                    list_id = None
            if list_id is None:
                continue
            try:
                self.ajustar_peso_mailing(list_id, 0, campaign_id=campaign_id)
                count += 1
            except Exception as e2:
                self.logger.info("Falha ao inativar lista_id=%s: %s", list_id, e2)
                continue
        if count:
            self.logger.info("Listas inativadas na campanha_id=%s: %s", campaign_id, count)
        return count

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    def _extract_id(self, data: Dict[str, Any], keys: List[str]) -> int:
        for key in keys:
            target = data
            parts = key.split(".")
            try:
                for part in parts:
                    target = target[part]
            except (KeyError, TypeError):
                continue
            if isinstance(target, int):
                return target
            if isinstance(target, str) and target.isdigit():
                return int(target)
        raise CreateMailingFailed("ID do mailing não encontrado na resposta")


# ---------------------------------------------------------------------------
# Execução automática (via .env)
# ---------------------------------------------------------------------------

def _normalizar_nome_campanha(nome: str) -> str:
    return nome.strip().lower()


def _encontrar_csv_campanha(base_dir: str, campanha: str) -> str | None:
    if not os.path.isdir(base_dir):
        return None
    alvo = _normalizar_nome_campanha(campanha)
    candidatos: list[tuple[str, float]] = []
    for fname in os.listdir(base_dir):
        if not fname.lower().endswith(".csv"):
            continue
        if _normalizar_nome_campanha(campanha) in _normalizar_nome_campanha(fname):
            fpath = os.path.join(base_dir, fname)
            try:
                mtime = os.path.getmtime(fpath)
            except Exception:
                mtime = 0.0
            candidatos.append((fpath, mtime))
    if not candidatos:
        return None
    # Escolher o mais recente
    candidatos.sort(key=lambda x: x[1], reverse=True)
    return candidatos[0][0]

# Extração desacoplada
# Função agora importada de src/extracao_bases.py: carregar_contatos_csv_semicolon


def main() -> None:
    """
    Atualiza automaticamente os leads (mailings) nas campanhas informadas via .env.

    Requisitos (.env):
    - THREECPLUS_BASE_URL
    - (opcional) THREECPLUS_API_TOKEN OU (THREECPLUS_USERNAME e THREECPLUS_PASSWORD)
    - THREECPLUS_TARGET_CAMPAIGNS: nomes das campanhas, separados por vírgula
    """
    load_dotenv()
    # Progressos simples
    print("Conectando ao 3C+...")

    auth = ThreeCAuthClient()
    # Se não houver token em ambiente, tentar login
    if not auth.is_autenticado:
        try:
            auth.login()
        except Exception as e:
            raise ThreeCMailingError(f"Falha na autenticação: {e}")

    mailing = ThreeCMailingClient(auth)

    alvo_raw = os.getenv("THREECPLUS_TARGET_CAMPAIGNS")
    if not alvo_raw:
        raise ThreeCMailingError("THREECPLUS_TARGET_CAMPAIGNS ausente no .env")

    campanhas_alvo = [s.strip() for s in alvo_raw.split(",") if s.strip()]
    print(f"Campanhas alvo: {len(campanhas_alvo)}")

    try:
        todas = mailing.listar_campanhas()
    except Exception as e:
        # Logar erro e abortar teste
        logging.getLogger("ThreeCMailingClient").error("Falha ao listar campanhas: %s", e)
        raise
    print(f"Campanhas disponíveis no 3C+: {len(todas)}")
    print("Campanhas encontradas (id - nome):")
    for c in todas:
        try:
            cid = c.get("id")
            nome = c.get("name")
            print(f"{cid} - {nome}")
        except Exception:
            pass

    base_dir = os.path.join("mailings", "campanhas")
    hoje = datetime.now().strftime("%Y-%m-%d")

    # Modo dry-run para testes (não cria/atualiza no 3C+)
    dry_run = str(os.getenv("THREECPLUS_DRY_RUN", "0")).lower() in ("1", "true", "yes")
    if dry_run:
        print("DRY-RUN ativo: nenhuma operação de escrita será realizada.")
        logging.getLogger("ThreeCMailingClient").info("DRY-RUN ativo")

    atualizados = 0
    for nome in campanhas_alvo:
        # localizar campanha no 3C+
        camp = next((c for c in todas if _normalizar_nome_campanha(nome) in _normalizar_nome_campanha(str(c.get("name", "")))), None)
        if not camp or "id" not in camp:
            print(f"Campanha não encontrada no 3C+: '{nome}'")
            continue
        campaign_id = int(camp["id"])

        # opção: deletar todas as listas antes de qualquer inclusão/atualização
        deletar_todas = str(os.getenv("THREECPLUS_DELETAR_TODAS", "0")).lower() in ("1", "true", "yes")
        if deletar_todas and not dry_run:
            try:
                listas_resp0 = mailing.listar_listas_da_campanha(campaign_id)
                itens0: list[dict] = []
                if isinstance(listas_resp0, dict):
                    for key in ("data", "lists", "items"):
                        v = listas_resp0.get(key)
                        if isinstance(v, list):
                            itens0 = v
                            break
                # Imprimir nomes/ids das listas antes da limpeza
                try:
                    total_antes = len(itens0)
                except Exception:
                    total_antes = 0
                if total_antes:
                    print(f"Listas antes da limpeza (campanha_id={campaign_id}): {total_antes}")
                    for it in itens0:
                        try:
                            lid_prev = mailing._extract_id(it, ["id", "list_id", "mailing_id"])
                        except Exception:
                            lid_prev = it.get("id") or it.get("list_id") or it.get("mailing_id")
                        nome_prev = it.get("name") or it.get("list_name") or it.get("mailing_name") or ""
                        print(f" - id={lid_prev} nome='{nome_prev}'")
                for it in itens0:
                    try:
                        lid0 = int(it.get("id") or it.get("list_id") or it.get("mailing_id"))
                    except Exception:
                        continue
                    try:
                        mailing.deletar_lista_da_campanha(campaign_id, lid0)
                    except Exception as e_del_all:
                        # fallback: peso=0 quando DELETE não é suportado
                        try:
                            mailing.ajustar_peso_mailing(lid0, 0, campaign_id=campaign_id)
                        except Exception:
                            logging.getLogger("ThreeCMailingClient").info("Deleção/peso=0 falhou para lista_id=%s: %s", lid0, e_del_all)
                print("Listas antigas removidas/inativadas")
            except Exception as e_list_all:
                logging.getLogger("ThreeCMailingClient").info("Falha ao deletar todas as listas: %s", e_list_all)

        # localizar CSV mais recente
        csv_path = _encontrar_csv_campanha(base_dir, nome)
        if not csv_path:
            print(f"CSV não encontrado para campanha: '{nome}' em {base_dir}")
            continue

        print(f"Atualizando campanha '{nome}' (id={campaign_id}) com '{os.path.basename(csv_path)}'")
        # Nome único para a nova lista (visível no 3C+)
        try:
            base_csv = os.path.splitext(os.path.basename(csv_path))[0]
        except Exception:
            base_csv = os.path.basename(csv_path)
        lista_nome_unico = f"Mailing {nome} - {base_csv} - {datetime.now().strftime('%Y%m%d-%H%M%S')}"
        # Idempotência: inativar listas existentes antes de criar nova
        resetar = str(os.getenv("THREECPLUS_RESET_LISTAS", "0")).lower() in ("1", "true", "yes")
        if resetar and not dry_run:
            try:
                q = mailing.inativar_todas_listas_da_campanha(campaign_id)
                print(f"Listas inativadas (peso=0) antes do upload: {q}")
            except Exception as e_reset:
                logging.getLogger("ThreeCMailingClient").info("Inativação prévia falhou: %s", e_reset)
        if dry_run:
            tam = os.path.getsize(csv_path)
            print(f"DRY-RUN: criaria container e enviaria '{os.path.basename(csv_path)}' bytes={tam}")
            logging.getLogger("ThreeCMailingClient").info(
                "DRY-RUN: campanha='%s' id=%s arquivo='%s' bytes=%s",
                nome, campaign_id, os.path.basename(csv_path), tam
            )
            continue
        try:
            modo_lista_unica = str(os.getenv("THREECPLUS_MODO_LISTA_UNICA", "0")).lower() in ("1", "true", "yes")
            if modo_lista_unica:
                # Atualizar lista existente; se não houver, criar uma nova e seguir atualizando
                listas_resp = mailing.listar_listas_da_campanha(campaign_id)
                listas: List[Dict[str, Any]] = []
                if isinstance(listas_resp, dict):
                    for key in ("data", "lists", "items"):
                        val = listas_resp.get(key)
                        if isinstance(val, list):
                            listas = val
                            break
                if not listas:
                    # criar lista nova via CSV 1-passo
                    colmap = {
                        "COD": "identifier",
                        "CPFCNPJ CLIENTE": "document",
                        "NOME / RAZAO SOCIAL": "name",
                        "CAMPANHA": "name",
                    }
                    for i in range(1, 21):
                        colmap[f"TELEFONE_{i}"] = "areacodephone"
                    created = mailing.criar_mailing_por_csv_em_campanha(
                        campaign_id,
                        csv_path,
                        filename=lista_nome_unico,
                        header=None,
                        colmap=colmap,
                    )
                    try:
                        list_id_new = mailing._extract_id(created, ["data.list_id", "list_id", "id"])
                        mailing.ajustar_peso_mailing(list_id_new, 100, campaign_id=campaign_id)
                        listas = [{"id": list_id_new}]
                        print(f"Lista criada (lista única): id={list_id_new} nome='{lista_nome_unico}'")
                    except Exception:
                        # não conseguimos extrair; reconsultar listas para obter id
                        try:
                            listas_resp_new = mailing.listar_listas_da_campanha(campaign_id)
                            tmp: List[Dict[str, Any]] = []
                            if isinstance(listas_resp_new, dict):
                                for key in ("data", "lists", "items"):
                                    v = listas_resp_new.get(key)
                                    if isinstance(v, list):
                                        tmp = v
                                        break
                            if tmp:
                                listas = tmp
                        except Exception as e_refresh:
                            logging.getLogger("ThreeCMailingClient").info("Reconsulta de listas após criação falhou: %s", e_refresh)
                # Escolhe maior id
                list_id = None
                try:
                    list_id = max(
                        [int(x.get("id") or x.get("list_id") or x.get("mailing_id")) for x in listas if (x.get("id") or x.get("list_id") or x.get("mailing_id"))],
                    )
                except Exception:
                    pass
                if not list_id:
                    raise ThreeCMailingError("Falha ao identificar lista para atualização")

                print(f"Atualizando lista existente via CSV: campanha_id={campaign_id} lista_id={list_id} arquivo={os.path.basename(csv_path)}")
                mailing.atualizar_lista_por_csv(campaign_id, list_id, csv_path)

                try:
                    mailing.ajustar_peso_mailing(list_id, 100, campaign_id=campaign_id)
                except Exception:
                    pass

                # Deleção opcional de listas antigas
                if str(os.getenv("THREECPLUS_DELETAR_ANTIGAS", "0")).lower() in ("1", "true", "yes"):
                    try:
                        listas_resp2 = mailing.listar_listas_da_campanha(campaign_id)
                        itens2: List[Dict[str, Any]] = []
                        if isinstance(listas_resp2, dict):
                            for key in ("data", "lists", "items"):
                                val = listas_resp2.get(key)
                                if isinstance(val, list):
                                    itens2 = val
                                    break
                        for it in itens2:
                            try:
                                cid = int(it.get("id") or it.get("list_id") or it.get("mailing_id"))
                            except Exception:
                                continue
                            if cid != list_id:
                                try:
                                    mailing.deletar_lista_da_campanha(campaign_id, cid)
                                except Exception as e_del:
                                    logging.getLogger("ThreeCMailingClient").info("Deleção falhou para lista_id=%s: %s", cid, e_del)
                    except Exception as e_del2:
                        logging.getLogger("ThreeCMailingClient").info("Listagem para deleção falhou: %s", e_del2)

                atualizados += 1
                tam = os.path.getsize(csv_path)
                print(f"OK (lista única): campanha_id={campaign_id} arquivo='{os.path.basename(csv_path)}' bytes={tam}")
                # Confirmação detalhada: listar nomes atuais
                try:
                    listas_resp = mailing.listar_listas_da_campanha(campaign_id)
                    itens_atual: List[Dict[str, Any]] = []
                    if isinstance(listas_resp, dict):
                        for key in ("data", "lists", "items"):
                            val = listas_resp.get(key)
                            if isinstance(val, list):
                                itens_atual = val
                                break
                    print(f"Listas atuais na campanha_id={campaign_id}: {len(itens_atual)}")
                    for it in itens_atual:
                        try:
                            lid_atual = mailing._extract_id(it, ["id", "list_id", "mailing_id"])
                        except Exception:
                            lid_atual = it.get("id") or it.get("list_id") or it.get("mailing_id")
                        nome_atual = it.get("name") or it.get("list_name") or it.get("mailing_name") or ""
                        print(f" - id={lid_atual} nome='{nome_atual}'")
                except Exception as e_conf_detalhe:
                    logging.getLogger("ThreeCMailingClient").info("Consulta detalhada de listas falhou: %s", e_conf_detalhe)
            else:
                # Fluxo tradicional: criar nova lista via CSV 1-passo
                colmap = {
                    "COD": "identifier",
                    "CPFCNPJ CLIENTE": "document",
                    "NOME / RAZAO SOCIAL": "name",
                    "CAMPANHA": "name",
                }
                for i in range(1, 21):
                    colmap[f"TELEFONE_{i}"] = "areacodephone"
                data = mailing.criar_mailing_por_csv_em_campanha(
                    campaign_id,
                    csv_path,
                    filename=lista_nome_unico,
                    header=None,
                    colmap=colmap,
                )
                try:
                    list_id = mailing._extract_id(data, ["data.list_id", "list_id", "id"])
                    mailing.ajustar_peso_mailing(list_id, 100, campaign_id=campaign_id)
                except Exception:
                    pass
                atualizados += 1
                tam = os.path.getsize(csv_path)
                print(f"OK (csv 1-passo): campanha_id={campaign_id} arquivo='{os.path.basename(csv_path)}' bytes={tam}")
                # Confirmação: consultar listas da campanha
                try:
                    listas_resp = mailing.listar_listas_da_campanha(campaign_id)
                    total_listas = 0
                    itens: List[Dict[str, Any]] = []
                    if isinstance(listas_resp, dict):
                        for key in ("data", "lists", "items"):
                            val = listas_resp.get(key)
                            if isinstance(val, list):
                                itens = val
                                total_listas = len(val)
                                break
                    print(f"Listas visíveis na campanha_id={campaign_id}: {total_listas}")
                    for it in itens:
                        try:
                            lid_atual = mailing._extract_id(it, ["id", "list_id", "mailing_id"])
                        except Exception:
                            lid_atual = it.get("id") or it.get("list_id") or it.get("mailing_id")
                        nome_atual = it.get("name") or it.get("list_name") or it.get("mailing_name") or ""
                        print(f" - id={lid_atual} nome='{nome_atual}'")
                except Exception as e_conf:
                    logging.getLogger("ThreeCMailingClient").info("Consulta de listas falhou: %s", e_conf)
        except Exception as e:
            print(f"Falha ao atualizar campanha '{nome}': {e}")
            logging.getLogger("ThreeCMailingClient").error("Falha ao atualizar campanha '%s': %s", nome, e)

        # Sempre tentar confirmar a quantidade de listas visíveis após a tentativa
        try:
            listas_resp2 = mailing.listar_listas_da_campanha(campaign_id)
            total_listas2 = 0
            if isinstance(listas_resp2, dict):
                for key in ("data", "lists", "items"):
                    val = listas_resp2.get(key)
                    if isinstance(val, list):
                        total_listas2 = len(val)
                        break
            print(f"Listas visíveis na campanha_id={campaign_id}: {total_listas2}")
        except Exception as e_conf2:
            logging.getLogger("ThreeCMailingClient").info("Consulta de listas pós-tentativa falhou: %s", e_conf2)

    print(f"Campanhas atualizadas: {atualizados}/{len(campanhas_alvo)}")


if __name__ == "__main__":  # execução direta
    main()
