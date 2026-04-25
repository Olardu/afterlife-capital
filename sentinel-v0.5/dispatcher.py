# dispatcher.py
# Agente orquestador central de Sentinel v0.5.
# Nodo raíz del grafo LangGraph. Coordina The Ear, CorrelationGuard,
# RegimeClassifier e Historian para tomar la decisión final de operar.
# Todas las llamadas al SDK de Alpaca (síncrono) se envuelven en asyncio.to_thread.

import asyncio
import logging
import math
from uuid import UUID

from config import (
    ALPACA_API_KEY,
    ALPACA_SECRET_KEY,
    KELLY_FRACTION,
    MAX_CAPITAL_PER_SENTINEL,
    MIN_CAPITAL_PER_SENTINEL,
)
from correlation_guard import CorrelationGuard
from historian import Historian
from regime_classifier import RegimeClassifier
from the_ear import TheEar

logger = logging.getLogger("sentinel.dispatcher")

_KILL_SWITCH_PASSPHRASE = "CONFIRMAR"

_REGIME_MULTIPLIERS = {
    "BULL":    1.0,
    "NEUTRAL": 0.75,
    "BEAR":    0.50,
}


class Dispatcher:
    def __init__(
        self,
        historian: Historian,
        the_ear: TheEar,
        correlation_guard: CorrelationGuard,
        regime_classifier: RegimeClassifier,
        owner_id: UUID,
    ):
        self.historian          = historian
        self.the_ear            = the_ear
        self.correlation_guard  = correlation_guard
        self.regime_classifier  = regime_classifier
        self.owner_id           = owner_id
        self.kill_switch_active = False
        self.open_positions: list[dict] = []   # [{ticker, qty, sentinel_id, side}]

    # -------------------------------------------------------------------------
    # Sincronización con Alpaca
    # -------------------------------------------------------------------------

    async def sync_positions_from_alpaca(self):
        """
        Reconstruye self.open_positions desde Alpaca (fuente de verdad).
        Loggea discrepancias entre el estado local y el de Alpaca.
        """
        try:
            alpaca_positions = await asyncio.to_thread(self._get_alpaca_positions)
        except Exception as e:
            logger.error(f"Error al sincronizar posiciones con Alpaca: {e}")
            return

        alpaca_tickers = {p["ticker"] for p in alpaca_positions}
        local_tickers  = {p["ticker"] for p in self.open_positions}

        ghost   = local_tickers - alpaca_tickers   # locales que Alpaca no conoce
        missing = alpaca_tickers - local_tickers   # en Alpaca pero no locales

        if ghost:
            logger.warning(f"Posiciones fantasma (local pero no en Alpaca): {ghost}")
        if missing:
            logger.warning(f"Posiciones no rastreadas (Alpaca pero no local): {missing}")

        self.open_positions = alpaca_positions
        logger.debug(f"Posiciones sincronizadas: {len(self.open_positions)} abiertas.")

    def _get_alpaca_positions(self) -> list[dict]:
        """Obtiene posiciones abiertas vía TradingClient. Ejecutado en thread."""
        from alpaca.trading.client import TradingClient

        client    = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)
        positions = client.get_all_positions()
        return [
            {
                "ticker":      p.symbol,
                "qty":         float(p.qty),
                "side":        "BUY" if float(p.qty) > 0 else "SELL",
                "sentinel_id": None,   # Alpaca no conoce el sentinel_id; se cruza por ticker si es necesario
            }
            for p in positions
        ]

    # -------------------------------------------------------------------------
    # Distribución de capital
    # -------------------------------------------------------------------------

    async def allocate_capital(self) -> dict[str, float]:
        """
        Calcula la asignación de capital (%) por Sentinel usando Half-Kelly
        ponderado por Sharpe ratio.

        Sentinels sin historial reciben MIN_CAPITAL_PER_SENTINEL.
        La suma total se normaliza para no exceder 100%.

        Returns:
            {str(sentinel_id): allocation_pct}
        """
        try:
            scores = await self.historian.get_sentinel_scores(owner_id=self.owner_id)
        except Exception as e:
            logger.error(f"Error al obtener performance scores: {e}")
            return {}

        if not scores:
            logger.info("Sin performance scores disponibles. Allocation vacía.")
            return {}

        allocation: dict[str, float] = {}
        sharpe_values = [max(s["sharpe_ratio"] or 0.0, 0.0) for s in scores]
        total_sharpe  = sum(sharpe_values)

        for score, sharpe in zip(scores, sharpe_values):
            sid = str(score["sentinel_id"])

            if total_sharpe == 0 or sharpe == 0:
                base = MIN_CAPITAL_PER_SENTINEL
            else:
                base = (sharpe / total_sharpe) * 100

            kelly_adjusted = base * KELLY_FRACTION
            clamped        = max(MIN_CAPITAL_PER_SENTINEL, min(MAX_CAPITAL_PER_SENTINEL, kelly_adjusted))
            allocation[sid] = clamped

        # Normalizar si la suma supera 100%
        total = sum(allocation.values())
        if total > 100.0:
            factor = 100.0 / total
            allocation = {sid: pct * factor for sid, pct in allocation.items()}
            logger.debug(f"Allocation normalizada (factor={factor:.4f}).")

        logger.info(f"Capital asignado: { {k: f'{v:.1f}%' for k, v in allocation.items()} }")
        return allocation

    # -------------------------------------------------------------------------
    # Ajuste por régimen
    # -------------------------------------------------------------------------

    def apply_regime_adjustment(self, allocation: dict, regime: str) -> dict:
        """
        Escala el capital asignado según el régimen del día:
            BULL    → 100% (sin cambios)
            NEUTRAL → 75%
            BEAR    → 50%

        Returns:
            Allocation ajustada {sentinel_id: allocation_pct}.
        """
        multiplier = _REGIME_MULTIPLIERS.get(regime, 1.0)

        if multiplier != 1.0:
            logger.info(f"Régimen {regime} — reduciendo allocation al {int(multiplier * 100)}%.")

        return {sid: pct * multiplier for sid, pct in allocation.items()}

    # -------------------------------------------------------------------------
    # Pipeline de señal
    # -------------------------------------------------------------------------

    async def process_signal(
        self,
        sentinel_id: UUID,
        owner_id: UUID,
        ticker: str,
        signal_type: str,
        price: float,
        qty: float,
        strategy_type: str = "",
        ear_state: dict = None,
        allocation: dict = None,
        account_equity: float = None,
    ) -> dict:
        """
        Pipeline completo de evaluación para una señal entrante.

        Etapas:
            1. Kill switch            — bloquea si activo
            2. The Ear                — bloquea si can_trade=False
            3. Régimen del día        — ajusta agresividad
            4. Allocation del Sentinel — determina qty máxima por capital
            5. CorrelationGuard       — ajusta qty por concentración
            6. Ejecución en Alpaca
            7. Persistencia en Historian

        ear_state:       si se provee (desde run_cycle), se usa directamente.
        allocation:      si se provee (desde run_cycle), se usa directamente.
        account_equity:  si se provee (desde run_cycle), evita una llamada
                         a Alpaca por señal para obtener el equity de cuenta.

        Returns:
            dict con approved, reason, signal_id, trade_id y qty_ejecutada.
        """
        base_result = {
            "approved":     False,
            "reason":       "",
            "signal_id":    None,
            "trade_id":     None,
            "qty_executed": 0.0,
        }

        # 1. Kill switch
        if self.kill_switch_active:
            logger.warning(f"Kill switch activo — señal {ticker} rechazada.")
            return {**base_result, "reason": "kill_switch_active"}

        # 2. The Ear — usar estado provisto por run_cycle o evaluar de forma independiente
        if ear_state is None:
            try:
                ear_state = await self.the_ear.evaluate()
            except Exception as e:
                logger.error(f"Error en The Ear al procesar {ticker}: {e}")
                ear_state = {"can_trade": False, "risk_score": 1.0, "circuit_breaker": False, "parking_brake": False}

        if not ear_state["can_trade"]:
            reason = (
                "circuit_breaker" if ear_state["circuit_breaker"]
                else "parking_brake"   if ear_state["parking_brake"]
                else "risk_score_veto"
            )
            logger.info(f"Señal {ticker} bloqueada por The Ear: {reason}.")
            return {**base_result, "reason": reason}

        # 3. Régimen → allocation ajustada
        regime = self.regime_classifier.get_regime()
        if allocation is None:
            try:
                allocation = await self.allocate_capital()
            except Exception as e:
                logger.error(f"Error en allocate_capital: {e}")
                allocation = {}
            allocation = self.apply_regime_adjustment(allocation, regime)

        # 4. Determinar qty máxima según allocation del Sentinel
        sentinel_alloc = allocation.get(str(sentinel_id), MIN_CAPITAL_PER_SENTINEL)
        if account_equity is None:
            try:
                account_equity = await asyncio.to_thread(self._get_account_equity)
            except Exception as e:
                logger.error(f"Error al obtener equity de cuenta: {e}")
                account_equity = 0.0

        if account_equity > 0 and price > 0:
            max_dollar_value = account_equity * (sentinel_alloc / 100.0)
            max_qty          = max_dollar_value / price
            qty              = min(qty, max_qty)

        # 5. CorrelationGuard
        try:
            scores = await self.historian.get_sentinel_scores(owner_id)
        except Exception as e:
            logger.error(f"Error al obtener scores para CorrelationGuard: {e}")
            scores = []

        try:
            guard_result = await self.correlation_guard.evaluate_signal(
                incoming_ticker    = ticker,
                incoming_qty       = qty,
                open_positions     = self.open_positions,
                performance_scores = scores,
            )
        except Exception as e:
            logger.error(f"Error en CorrelationGuard: {e}. Aprobando con qty original.")
            guard_result = {"approved": True, "adjusted_qty": qty, "avg_correlation": 0.0, "reason": "approved"}

        if not guard_result["approved"]:
            logger.info(f"Señal {ticker} descartada por CorrelationGuard: {guard_result['reason']}.")
            return {**base_result, "reason": guard_result["reason"]}

        final_qty = guard_result["adjusted_qty"]

        # 6. Ejecutar orden en Alpaca
        # v0.5 es long-only. Short selling se habilita explícitamente cuando se
        # implementen estrategias que lo requieran.
        side = "BUY" if signal_type == "BUY" else "SELL"
        if side == "SELL":
            has_position = any(p["ticker"] == ticker for p in self.open_positions)
            if not has_position:
                logger.info(f"Señal SELL para {ticker} rechazada — sin posición abierta.")
                return {**base_result, "reason": "no_open_position"}
        try:
            order_result = await self.execute_order(
                ticker        = ticker,
                side          = side,
                qty           = final_qty,
                strategy_type = strategy_type,
                limit_price   = price if self._is_limit_strategy(strategy_type) else None,
            )
        except Exception as e:
            logger.error(f"Error al ejecutar orden {ticker}: {e}")
            order_result = {"status": "CANCELLED", "filled_price": None, "order_id": None}

        # 7. Persistir en Historian
        try:
            signal_id = await self.historian.record_signal(
                sentinel_id     = sentinel_id,
                owner_id        = owner_id,
                ticker          = ticker,
                signal_type     = signal_type,
                price_at_signal = price,
            )
            slippage = (
                order_result["filled_price"] - price
                if order_result.get("filled_price") is not None else None
            )
            trade_id = await self.historian.record_trade(
                signal_id    = signal_id,
                sentinel_id  = sentinel_id,
                owner_id     = owner_id,
                ticker       = ticker,
                side         = side,
                qty          = final_qty,
                filled_price = order_result.get("filled_price"),
                slippage     = slippage,
                status       = order_result.get("status", "PENDING"),
            )
        except Exception as e:
            logger.error(f"Error al persistir señal/trade en Historian: {e}")
            signal_id = None
            trade_id  = None

        # Actualizar posiciones locales si se ejecutó
        if order_result.get("status") == "FILLED":
            self.open_positions.append({
                "ticker":      ticker,
                "qty":         final_qty,
                "side":        side,
                "sentinel_id": sentinel_id,
            })

        approved = order_result.get("status") != "CANCELLED"
        logger.info(
            f"Pipeline completo | {ticker} {side} qty={final_qty:.2f} "
            f"status={order_result.get('status')} regime={regime} "
            f"correlation={guard_result['avg_correlation']:.4f}"
        )
        return {
            "approved":     approved,
            "reason":       order_result.get("status", "PENDING"),
            "signal_id":    signal_id,
            "trade_id":     trade_id,
            "qty_executed": final_qty if approved else 0.0,
        }

    # -------------------------------------------------------------------------
    # Ejecución de órdenes
    # -------------------------------------------------------------------------

    @staticmethod
    def _is_limit_strategy(strategy_type: str) -> bool:
        st = strategy_type.lower()
        return "mean_reversion" in st or "pairs" in st

    async def execute_order(
        self,
        ticker: str,
        side: str,
        qty: float,
        strategy_type: str = "",
        limit_price: float = None,
    ) -> dict:
        """
        Envía una orden a Alpaca con Smart Routing:
            mean_reversion / pairs → Limit Order al precio de señal
            Cualquier otra estrategia → Market Order

        Limit Orders: espera 60s y verifica si se ejecutó. Si no está FILLED,
        cancela y retorna status CANCELLED.

        Returns:
            {order_id, filled_price, status}
        """
        is_limit = self._is_limit_strategy(strategy_type) and limit_price is not None

        original_qty = qty
        qty = int(math.floor(qty))
        if qty < 1:
            logger.info(
                f"Qty {original_qty:.4f} redondeada a 0 para {ticker} {side} — orden cancelada."
            )
            return {"order_id": None, "filled_price": None, "status": "CANCELLED"}

        try:
            submit_result = await asyncio.to_thread(
                self._submit_order_sync, ticker, side, qty, strategy_type, limit_price
            )
        except Exception as e:
            logger.error(f"Alpaca rechazó la orden {ticker} {side} qty={qty}: {e}")
            return {"order_id": None, "filled_price": None, "status": "CANCELLED"}

        if not is_limit:
            return submit_result

        # Timeout de 60s para limit orders
        order_id = submit_result.get("order_id")
        if not order_id:
            return submit_result

        logger.info(f"Limit order {order_id} enviada — esperando 60s para confirmar fill.")
        await asyncio.sleep(60)

        try:
            return await asyncio.to_thread(self._check_and_cancel_limit_sync, order_id)
        except Exception as e:
            logger.error(f"Error al verificar limit order {order_id}: {e}")
            return {"order_id": order_id, "filled_price": None, "status": "CANCELLED"}

    def _submit_order_sync(
        self,
        ticker: str,
        side: str,
        qty: float,
        strategy_type: str,
        limit_price: float,
    ) -> dict:
        """Construye y envía la orden. Ejecutado en thread separado."""
        from alpaca.trading.client import TradingClient
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest

        client      = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)
        order_side  = OrderSide.BUY if side == "BUY" else OrderSide.SELL
        use_limit   = self._is_limit_strategy(strategy_type) and limit_price is not None

        if use_limit:
            order_data = LimitOrderRequest(
                symbol       = ticker,
                qty          = qty,
                side         = order_side,
                time_in_force = TimeInForce.DAY,
                limit_price  = round(limit_price, 2),
            )
        else:
            order_data = MarketOrderRequest(
                symbol        = ticker,
                qty           = qty,
                side          = order_side,
                time_in_force = TimeInForce.DAY,
            )

        order = client.submit_order(order_data)

        filled_price = float(order.filled_avg_price) if order.filled_avg_price else None
        status       = order.status.value.upper() if order.status else "PENDING"

        logger.info(
            f"Orden enviada: {ticker} {side} qty={qty} "
            f"type={'LIMIT' if use_limit else 'MARKET'} "
            f"status={status} filled={filled_price}"
        )
        return {
            "order_id":    str(order.id),
            "filled_price": filled_price,
            "status":       status,
        }

    def _check_and_cancel_limit_sync(self, order_id: str) -> dict:
        """Verifica si la limit order se ejecutó. Si no, la cancela. Ejecutado en thread."""
        from alpaca.trading.client import TradingClient

        client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)
        order  = client.get_order_by_id(order_id)
        status = order.status.value.upper() if order.status else "PENDING"

        if status == "FILLED":
            logger.info(f"Limit order {order_id} ejecutada exitosamente.")
            return {
                "order_id":    order_id,
                "filled_price": float(order.filled_avg_price) if order.filled_avg_price else None,
                "status":       "FILLED",
            }

        try:
            client.cancel_order_by_id(order_id)
            logger.info(f"Limit order {order_id} cancelada por timeout (60s sin fill).")
        except Exception as e:
            logger.warning(f"Error al cancelar limit order {order_id}: {e}")

        return {"order_id": order_id, "filled_price": None, "status": "CANCELLED"}

    def _get_account_equity(self) -> float:
        """Retorna equity de la cuenta paper. Ejecutado en thread separado."""
        from alpaca.trading.client import TradingClient

        client  = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)
        account = client.get_account()
        return float(account.equity)

    # -------------------------------------------------------------------------
    # Kill switch
    # -------------------------------------------------------------------------

    async def activate_kill_switch(self, confirmation: str):
        """
        Confirmación de dos pasos. Solo procede si confirmation == 'CONFIRMAR'.
        Cancela todas las órdenes pendientes y liquida todas las posiciones.
        """
        if confirmation != _KILL_SWITCH_PASSPHRASE:
            logger.warning(
                f"Kill switch rechazado — confirmación incorrecta. "
                f"Enviar '{_KILL_SWITCH_PASSPHRASE}' para activar."
            )
            return

        logger.critical("KILL SWITCH ACTIVADO — cerrando todas las posiciones.")
        try:
            await asyncio.to_thread(self._close_all_sync)
        except Exception as e:
            logger.critical(f"Error durante liquidación del kill switch: {e}")

        self.kill_switch_active = True
        self.open_positions.clear()
        logger.critical("Kill switch activo. Sistema en standby.")

    async def deactivate_kill_switch(self, confirmation: str):
        """Reactiva el sistema. Requiere confirmación 'CONFIRMAR'."""
        if confirmation != _KILL_SWITCH_PASSPHRASE:
            logger.warning("Desactivación de kill switch rechazada — confirmación incorrecta.")
            return

        self.kill_switch_active = False
        logger.info("Kill switch desactivado. Sistema reactivado.")

    def _close_all_sync(self):
        """Cancela órdenes abiertas y cierra posiciones vía Alpaca. Ejecutado en thread."""
        from alpaca.trading.client import TradingClient

        client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)
        client.cancel_orders()
        client.close_all_positions(cancel_orders=True)
        logger.info("Todas las órdenes canceladas y posiciones liquidadas.")

    # -------------------------------------------------------------------------
    # Ciclo principal
    # -------------------------------------------------------------------------

    async def run_cycle(self, pending_signals: list[dict] = None):
        """
        Ciclo principal del Dispatcher. Llamado por el grafo LangGraph en cada tick.

        Flujo:
            1. Sincronizar posiciones con Alpaca
            2. Clasificar régimen del día (idempotente, una vez por día)
            3. Evaluar macro con The Ear
            4. Procesar señales pendientes si can_trade
            5. Evaluar performance decay en Sentinels activos

        pending_signals: lista de señales de los Sentinels con formato
            [{sentinel_id, owner_id, ticker, signal_type, price, qty, strategy_type}]
        """
        if self.kill_switch_active:
            logger.warning("run_cycle omitido — kill switch activo.")
            return

        # 1. Sincronizar posiciones
        await self.sync_positions_from_alpaca()

        # 2. Régimen del día (idempotente)
        try:
            regime = await self.regime_classifier.classify_today()
        except Exception as e:
            logger.error(f"Error en RegimeClassifier: {e}")
            regime = self.regime_classifier.get_regime()

        # 3. Evaluar macro
        try:
            ear_state = await self.the_ear.evaluate()
        except Exception as e:
            logger.error(f"Error en The Ear durante run_cycle: {e}")
            ear_state = {"can_trade": False}

        can_trade = ear_state.get("can_trade", False)

        # 4. Procesar señales si el sistema puede operar
        # Calcular allocation una sola vez (ear_state y allocation se pasan a cada señal)
        results = []
        if can_trade and pending_signals:
            try:
                cycle_allocation = await self.allocate_capital()
                cycle_allocation = self.apply_regime_adjustment(cycle_allocation, regime)
            except Exception as e:
                logger.error(f"Error calculando allocation en run_cycle: {e}")
                cycle_allocation = {}

            try:
                cycle_equity = await asyncio.to_thread(self._get_account_equity)
            except Exception as e:
                logger.error(f"Error obteniendo equity en run_cycle: {e}")
                cycle_equity = 0.0

            for signal in pending_signals:
                try:
                    result = await self.process_signal(
                        **signal,
                        ear_state      = ear_state,
                        allocation     = cycle_allocation,
                        account_equity = cycle_equity,
                    )
                    results.append(result)
                except Exception as e:
                    logger.error(f"Error procesando señal {signal.get('ticker')}: {e}")
        elif not can_trade:
            logger.info(f"Señales omitidas — can_trade=False (régimen={regime}).")

        # 5. Evaluar decay en todos los Sentinels activos del owner (fuente de verdad: DB).
        # Multi-ticker: cada Sentinel evalúa decay por cada uno de sus tickers asignados.
        try:
            active_sentinels = await self.historian.get_active_sentinels(self.owner_id)
        except Exception as e:
            logger.error(f"Error al obtener sentinels activos para decay: {e}")
            active_sentinels = []

        for sentinel in active_sentinels:
            sentinel_id = sentinel["sentinel_id"]
            tickers     = sentinel.get("tickers") or []
            for ticker in tickers:
                try:
                    await self.historian.evaluate_decay(sentinel_id=sentinel_id, ticker=ticker)
                except Exception as e:
                    logger.error(f"Error evaluando decay ({sentinel_id}, {ticker}): {e}")

        approved_count = sum(1 for r in results if r.get("approved"))
        logger.info(
            f"Ciclo completado — régimen={regime} can_trade={can_trade} "
            f"señales={len(results)} aprobadas={approved_count}"
        )
