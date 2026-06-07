# alc_g/core_runner.py
# Orquestador del runtime ALC-G Fase 0. Lee la cuenta #2 (vía broker DIP),
# arma el CycleReport con la lógica pura de core.py, y lo REPORTA (modo informe:
# no ejecuta órdenes). Mantiene el estado del modo auto VIX entre ciclos.
#
# Independiente del bot Sentinel. NO importa dispatcher/main. Spec: Deep #105.

from __future__ import annotations

import logging
from decimal import Decimal

from alc_g.alcg_client import Broker
from alc_g.config_alc_g import AlcgParams
from alc_g.core import (
    AccountSnapshot,
    CycleReport,
    VixState,
    build_cycle_report,
    dca_floor_deposit,
    step_vix_auto,
    target_exposure_by_ticker,
)

logger = logging.getLogger("alc_g.runner")


def report_to_dict(r: CycleReport) -> dict:
    """Serializa el CycleReport a JSON-safe (Decimal -> str) para la API/UI."""
    return {
        "target_leverage": str(r.target_leverage),
        "effective_leverage": str(r.effective_leverage),
        "real_leverage": str(r.real_leverage),
        "gap": str(r.gap),
        "needs_rebalance": r.needs_rebalance,
        "glide_ceiling": str(r.glide_ceiling),
        "vix_capped": r.vix_capped,
        "equity": str(r.equity),
        "long_value": str(r.long_value),
        "drifted": list(r.drifted),
    }


class AlcgRunner:
    """Runtime ALC-G. Un ciclo = leer cuenta #2 -> calcular -> reportar.

    `mode` viene de params: 'informe' (default, no ejecuta) | 'ejecutar' (GO Roman).
    Mantiene `vix_state` (histéresis del modo auto) y el último reporte para la API.
    """

    def __init__(self, broker: Broker, params: AlcgParams | None = None):
        self._broker = broker
        self.params = params or AlcgParams()
        self.vix_state = VixState()
        self.last_report: CycleReport | None = None

    # --- cálculo de un ciclo (sin I/O de escritura) -------------------------

    def evaluate(self, account: AccountSnapshot, vix_close: Decimal | None) -> CycleReport:
        """Avanza el modo auto (si hay VIX) y arma el reporte. Puro respecto a
        la cuenta (la lectura la hizo el caller)."""
        if vix_close is not None:
            self.vix_state = step_vix_auto(self.vix_state, vix_close, self.params)
        report = build_cycle_report(account, self.vix_state, self.params)
        self.last_report = report
        return report

    def planned_orders(self, report: CycleReport, account: AccountSnapshot) -> list[dict]:
        """Órdenes de rebalanceo que se MANDARÍAN para cerrar el gap/drift
        (informe: se calculan y muestran, no se envían). delta>0 = comprar."""
        target = target_exposure_by_ticker(report.equity, report.effective_leverage, self.params)
        orders: list[dict] = []
        for ticker, tgt_value in target.items():
            current = account.positions.get(ticker, Decimal("0"))
            delta = tgt_value - current
            orders.append({
                "ticker": ticker,
                "target_value": str(tgt_value),
                "current_value": str(current),
                "delta_value": str(delta),
                "side": "BUY" if delta > 0 else ("SELL" if delta < 0 else "HOLD"),
            })
        return orders

    # --- ejecución del rebalanceo (modo ejecutar) ---------------------------

    def execute_rebalance(self) -> dict:
        """Lee la cuenta #2, arma el plan y LO EJECUTA en la cuenta (BUY por
        notional / SELL por acciones enteras, market DAY). Sólo se llama tras la
        confirmación del cockpit. Devuelve el reporte + plan + resultados de las
        órdenes enviadas. El gate de seguridad real vive en el broker
        (allow_execute) y en el endpoint (confirm)."""
        account = self._broker.get_snapshot()
        vix = self._broker.get_vix_close()
        report = self.evaluate(account, vix)
        orders = self.planned_orders(report, account)
        results = self._broker.submit_rebalance(
            orders, min_order_usd=self.params.min_order_usd, p=self.params,
        )
        sent = [r for r in results if not r.get("skipped")]
        logger.warning(
            "ALC-G REBALANCEO EJECUTADO | preset=%s eff_lev=%s órdenes=%d (enviadas=%d)",
            self.params.preset, report.effective_leverage, len(results), len(sent),
        )
        return {
            "mode": self.params.mode,
            "preset": self.params.preset,
            "report": report_to_dict(report),
            "planned_orders": orders,
            "results": results,
            "sent_count": len(sent),
            "min_order_usd": str(self.params.min_order_usd),
        }

    # --- un ciclo completo (con lectura de la cuenta) -----------------------

    def run_once(self) -> dict:
        """Lee la cuenta #2, evalúa y devuelve el reporte + plan (modo informe).
        Loguea el resumen. NO ejecuta órdenes."""
        account = self._broker.get_snapshot()
        vix = self._broker.get_vix_close()
        report = self.evaluate(account, vix)
        orders = self.planned_orders(report, account)
        deposit = dca_floor_deposit(account.equity, self.params)

        logger.info(
            "ALC-G ciclo | target=%s real=%s gap=%s techo=%s rebal=%s vix_cap=%s "
            "equity=%s drift=%s aporte_piso=%s",
            report.target_leverage, report.real_leverage, report.gap,
            report.glide_ceiling, report.needs_rebalance, report.vix_capped,
            report.equity, list(report.drifted), deposit,
        )
        if self.params.mode == "ejecutar":
            logger.warning("ALC-G mode=ejecutar pero la ejecución requiere GO de Roman; "
                           "no se enviaron órdenes en Fase 0.")

        return {
            "mode": self.params.mode,
            "preset": self.params.preset,
            "report": report_to_dict(report),
            "planned_orders": orders,
            "floor_deposit": str(deposit),
            "vix_state": {"capped": self.vix_state.capped,
                          "release_streak": self.vix_state.release_streak},
        }
