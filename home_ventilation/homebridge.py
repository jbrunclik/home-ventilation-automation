import logging

import httpx

logger = logging.getLogger(__name__)


class HomebridgeClient:
    def __init__(self, host: str, port: int, username: str, password: str) -> None:
        self._base_url = f"http://{host}:{port}"
        self._username = username
        self._password = password
        self._token: str | None = None
        self._client = httpx.AsyncClient(timeout=10.0)

    async def close(self) -> None:
        await self._client.aclose()

    async def _login(self) -> None:
        resp = await self._client.post(
            f"{self._base_url}/api/auth/login",
            json={"username": self._username, "password": self._password},
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        logger.info("Authenticated with Homebridge")

    def _auth_headers(self) -> dict[str, str]:
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        return {}

    async def _get_accessories(self) -> list[dict]:
        if not self._token:
            await self._login()

        resp = await self._client.get(
            f"{self._base_url}/api/accessories",
            headers=self._auth_headers(),
        )

        if resp.status_code == 401:
            logger.info("Token expired, re-authenticating")
            await self._login()
            resp = await self._client.get(
                f"{self._base_url}/api/accessories",
                headers=self._auth_headers(),
            )

        resp.raise_for_status()
        return resp.json()

    def _find_characteristic(
        self, accessories: list[dict], accessory_name: str, characteristic_type: str
    ) -> float | None:
        for accessory in accessories:
            name = accessory.get("serviceName", "")
            if name != accessory_name:
                continue
            for char in accessory.get("serviceCharacteristics", []):
                if char.get("type") == characteristic_type:
                    return char.get("value")
        return None

    async def get_co2(self, accessory_name: str) -> int | None:
        try:
            accessories = await self._get_accessories()
            value = self._find_characteristic(accessories, accessory_name, "CarbonDioxideLevel")
            if value is not None:
                return int(value)
            logger.warning("CO2 value not found for accessory '%s'", accessory_name)
            return None
        except Exception:
            logger.exception("Failed to read CO2 for '%s'", accessory_name)
            return None

    async def get_humidity(self, accessory_name: str) -> float | None:
        try:
            accessories = await self._get_accessories()
            value = self._find_characteristic(
                accessories, accessory_name, "CurrentRelativeHumidity"
            )
            if value is not None:
                return float(value)
            logger.warning("Humidity value not found for accessory '%s'", accessory_name)
            return None
        except Exception:
            logger.exception("Failed to read humidity for '%s'", accessory_name)
            return None
