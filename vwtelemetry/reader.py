"""Read the VW EU Data Act portal via the low-level EudaApiClient (NOT CarConnectivity.fetch_all,
which merges all datasets in one blocking call and hangs). Auto-discovers all vehicles; yields one
raw record per content-bearing dataset not already ingested."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

from .config import Config


def _default_factory(user: str, pw: str, country: str) -> Any:
    from carconnectivity_connectors.vw_eu_data_act.client import EudaApiClient

    return EudaApiClient(user, pw, country=country, accept_terms_on_login=True)


class Reader:
    def __init__(
        self, config: Config, client_factory: Callable[[str, str, str], Any] | None = None
    ) -> None:
        self._cfg = config
        self._factory = client_factory or _default_factory

    def iter_new_records(self, seen: dict[str, set[str]]) -> Iterator[dict[str, Any]]:
        c = self._factory(self._cfg.vwid_user, self._cfg.vwid_password, self._cfg.country)
        c.ensure_login()
        for veh in c.list_vehicles():
            vin = veh.get("vin")
            if not vin or (self._cfg.vin_allowlist and vin not in self._cfg.vin_allowlist):
                continue
            ident = c.get_metadata(vin, request_type="partial").get("Identifier")
            if not ident:
                continue
            already = seen.get(vin, set())
            for d in c.list_datasets(vin, ident, request_type="partial"):
                name = d.get("name", "")
                if not name or "no_content_found" in name or name in already:
                    continue
                data = c.download_dataset(vin, ident, name, request_type="partial")
                rows = data.get("Data", []) if isinstance(data, dict) else []
                fields = {
                    r.get("dataFieldName"): r.get("value") for r in rows if r.get("dataFieldName")
                }
                tss = [r.get("timestampUtc") for r in rows if r.get("timestampUtc")]
                captured = max(tss).replace("Z", "+00:00") if tss else None
                yield {
                    "dataset": name,
                    "ts": name.split("_", 1)[0],
                    "vin": vin,
                    "brand": self._cfg.brand,
                    "captured_at": captured,
                    "fields": fields,
                }
