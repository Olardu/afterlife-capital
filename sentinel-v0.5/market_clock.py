# market_clock.py
# Helper público para conocer el estado del mercado NYSE y el tiempo
# hasta el próximo cambio de estado (#FIX-011).
#
# El bot ya usa MARKET_OPEN / MARKET_CLOSE / PARKING_BRAKE_TIME / TIMEZONE
# de config.py, pero ese horario solo cubre la sesión regular. Acá
# agregamos:
#   - Pre-market (04:00–09:30 ET).
#   - After-hours (16:00–20:00 ET).
#   - Calendario de holidays NYSE.
#   - Cálculo de próxima apertura / cierre considerando fines de semana
#     y holidays.
#
# Sin dependencias nuevas (`pandas_market_calendars` no está en
# requirements.txt y no queremos sumar peso). Los holidays se mantienen
# manualmente — actualizar la lista cuando NYSE publique el calendario
# del año siguiente.

from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from config import MARKET_CLOSE, MARKET_OPEN, TIMEZONE


_PRE_MARKET_OPEN  = time(4, 0)
_REGULAR_OPEN     = time(*map(int, MARKET_OPEN.split(":")))
_REGULAR_CLOSE    = time(*map(int, MARKET_CLOSE.split(":")))
_AFTER_HOURS_END  = time(20, 0)


# Calendario NYSE — observed dates. Mantener actualizado anualmente.
# Fuente: nyse.com/markets/hours-calendars
# Cobertura: 2026-2027 (suficiente para la operación actual de Sentinel).
_NYSE_HOLIDAYS: set[date] = {
    # 2026
    date(2026, 1, 1),    # New Year's Day
    date(2026, 1, 19),   # MLK Day
    date(2026, 2, 16),   # Presidents Day
    date(2026, 4, 3),    # Good Friday
    date(2026, 5, 25),   # Memorial Day
    date(2026, 6, 19),   # Juneteenth
    date(2026, 7, 3),    # Independence Day (observed — Jul 4 cae sábado)
    date(2026, 9, 7),    # Labor Day
    date(2026, 11, 26),  # Thanksgiving
    date(2026, 12, 25),  # Christmas
    # 2027
    date(2027, 1, 1),    # New Year's Day
    date(2027, 1, 18),   # MLK Day
    date(2027, 2, 15),   # Presidents Day
    date(2027, 3, 26),   # Good Friday
    date(2027, 5, 31),   # Memorial Day
    date(2027, 6, 18),   # Juneteenth (observed — Jun 19 cae sábado)
    date(2027, 7, 5),    # Independence Day (observed — Jul 4 cae domingo)
    date(2027, 9, 6),    # Labor Day
    date(2027, 11, 25),  # Thanksgiving
    date(2027, 12, 24),  # Christmas (observed — Dec 25 cae sábado)
}


def _tz() -> ZoneInfo:
    return ZoneInfo(TIMEZONE)


def _is_trading_day(d: date) -> bool:
    """True si d es un día hábil NYSE (no fin de semana, no holiday)."""
    if d.weekday() >= 5:   # 5=sábado, 6=domingo
        return False
    if d in _NYSE_HOLIDAYS:
        return False
    return True


def _classify(now_et: datetime) -> str:
    """Clasifica el estado del mercado en el momento now_et (ya en ET)."""
    today = now_et.date()
    if not _is_trading_day(today):
        return "CLOSED"
    t = now_et.time()
    if t < _PRE_MARKET_OPEN:
        return "CLOSED"
    if t < _REGULAR_OPEN:
        return "PRE_MARKET"
    if t < _REGULAR_CLOSE:
        return "OPEN"
    if t < _AFTER_HOURS_END:
        return "AFTER_HOURS"
    return "CLOSED"


def _next_regular_open(now_et: datetime) -> datetime:
    """Próximo timestamp de apertura regular (09:30 ET) >= now_et."""
    today = now_et.date()
    today_open = datetime.combine(today, _REGULAR_OPEN, tzinfo=_tz())
    if _is_trading_day(today) and now_et < today_open:
        return today_open
    candidate = today + timedelta(days=1)
    while not _is_trading_day(candidate):
        candidate += timedelta(days=1)
    return datetime.combine(candidate, _REGULAR_OPEN, tzinfo=_tz())


def _today_regular_close(now_et: datetime) -> Optional[datetime]:
    """Timestamp de cierre regular hoy (16:00 ET) si hoy es trading day y aún
    no se superó. None en otro caso."""
    today = now_et.date()
    if not _is_trading_day(today):
        return None
    today_close = datetime.combine(today, _REGULAR_CLOSE, tzinfo=_tz())
    return today_close if now_et < today_close else None


def get_market_status() -> dict:
    """
    Estado del mercado NYSE + tiempos hasta próximo cambio de estado.

    Returns:
        {
            "is_open":         bool,    # True solo si status == "OPEN" (sesión regular)
            "status":          str,     # "OPEN" | "CLOSED" | "PRE_MARKET" | "AFTER_HOURS"
            "next_open":       str|None, # ISO 8601 con offset, cuando re-abre la sesión regular
            "next_close":      str|None, # ISO 8601 con offset, cuando cierra (solo si OPEN)
            "current_time_et": str,      # ISO 8601 con offset
        }
    """
    now_et = datetime.now(tz=_tz())
    status = _classify(now_et)
    is_open = status == "OPEN"

    next_open  = _next_regular_open(now_et) if not is_open else None
    next_close = _today_regular_close(now_et) if is_open else None

    return {
        "is_open":         is_open,
        "status":          status,
        "next_open":       next_open.isoformat() if next_open else None,
        "next_close":      next_close.isoformat() if next_close else None,
        "current_time_et": now_et.isoformat(),
    }


if __name__ == "__main__":  # pragma: no cover
    import json
    s = get_market_status()
    print(json.dumps(s, indent=2))
