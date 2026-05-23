# dispatcher.py
# Agente orquestador central de Sentinel v0.5.
# Nodo raíz del grafo LangGraph. Coordina The Ear, CorrelationGuard,
# RegimeClassifier e Historian para tomar la decisión final de operar.
# Todas las llamadas al SDK de Alpaca (síncrono) se envuelven en asyncio.to_thread.
#
# Índice (secciones buscables por marcador "§ N"):
#   § 1 — Imports y configuración
#   § 2 — Inicialización (Dispatcher.__init__)
#   § 3 — Sincronización con Alpaca
#   § 4 — Distribución de capital (allocate_capital, apply_regime_adjustment)
#   § 5 — Pipeline de señal (process_signal, _apply_fill_to_cache)
#   § 6 — Ejecución de órdenes
#   § 7 — Kill switch
#   § 8 — Ciclo principal (run_cycle)

# ════════════════════════════════════════════════════════════
# § 1 — Imports y configuración
# ════════════════════════════════════════════════════════════
import asyncio
import logging
import math
from decimal import Decimal
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

# Strategy types que ejecutan como Limit order (precio de señal). El resto
# va como Market. Se usa set explícito en lugar de substring matching para
# evitar el bug de bollinger_bounce/etc. NO ejecutando como limit por no
# contener la palabra "mean_reversion" en su strategy_type.
_LIMIT_STRATEGIES = {
    "bollinger_bounce",
    "rsi_short",
    "vwap_reversion",
    "bollinger_squeeze",
    "rsi_divergence",
}


# ════════════════════════════════════════════════════════════
# § 2 — Inicialización
# ════════════════════════════════════════════════════════════
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
        # Indexado por ticker para detección O(1) de duplicados intra-cycle (#H-5).
        # Estructura: {ticker: {ticker, qty, sentinel_id, side}}
        self.open_positions: dict[str, dict] = {}

    # ════════════════════════════════════════════════════════
    # § 3 — Sincronización con Alpaca
    # ════════════════════════════════════════════════════════

    async def sync_positions_from_alpaca(self):
        """
        Reconstruye self.open_positions desde Alpaca (fuente de verdad).
        Loggea discrepancias entre el estado local y el de Alpaca.
        """
        try:
            alpaca_positions = await asyncio.wait_for(
                asyncio.to_thread(self._get_alpaca_positions),
                timeout=15.0,
            )
        except asyncio.TimeoutError:
            logger.error("Timeout (15s) al sincronizar posiciones con Alpaca")
            return
        except Exception as e:
            logger.error(f"Error al sincronizar posiciones con Alpaca: {e}")
            return

        alpaca_tickers = set(alpaca_positions.keys())
        local_tickers  = set(self.open_positions.keys())

        ghost   = local_tickers - alpaca_tickers   # locales que Alpaca no conoce
        missing = alpaca_tickers - local_tickers   # en Alpaca pero no locales

        if ghost:
            logger.warning(f"Posiciones fantasma (local pero no en Alpaca): {ghost}")
        if missing:
            logger.warning(f"Posiciones no rastreadas (Alpaca pero no local): {missing}")

        self.open_positions = alpaca_positions
        logger.debug(f"Posiciones sincronizadas: {len(self.open_positions)} abiertas.")

    def _get_alpaca_positions(self) -> dict[str, dict]:
        """Obtiene posiciones abiertas vía TradingClient. Ejecutado en thread.

        Returns:
            {ticker: {ticker, qty, side, sentinel_id}}. Indexado por ticker
            para que el caller (sync_positions_from_alpaca) reemplace el dict
            entero sin tener que reconstruirlo.
        """
        from alpaca.trading.client import TradingClient

        client    = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)
        positions = client.get_all_positions()
        # qty viene del SDK Alpaca como string → Decimal (#H-4), computado una vez.
        result: dict[str, dict] = {}
        for p in positions:
            qty_dec = Decimal(str(p.qty))
            result[p.symbol] = {
                "ticker":      p.symbol,
                "qty":         qty_dec,
                "side":        "BUY" if qty_dec > 0 else "SELL",
                "sentinel_id": None,   # Alpaca no conoce el sentinel_id; se cruza por ticker si es necesario
            }
        return result

    # ════════════════════════════════════════════════════════
    # § 4 — Distribución de capital
    # ════════════════════════════════════════════════════════

    async def allocate_capital(self) -> dict[str, float]:
        """
        Calcula la asignación de capital (%) por Sentinel usando Half-Kelly
        ponderado por Sharpe ratio.

        Los scores vienen per-ticker desde performance_scores. Esta función
        los agrega a nivel Sentinel usando promedio ponderado por total_trades:
            sentinel_sharpe = Σ(sharpe_i × trades_i) / Σ(trades_i)

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

        # --- Paso 1: Agregar per-ticker → per-sentinel (promedio ponderado) ---
        # Conversión explícita float()/int(): asyncpg devuelve NUMERIC como
        # decimal.Decimal y INTEGER como int, pero ambos se mezclan con los
        # acumuladores float que inicializamos abajo. Sin esta conversión el
        # `+=` lanza TypeError("unsupported operand type(s) for +=: 'float'
        # and 'decimal.Decimal'"). Cierra el #H-4 en este punto y queda como
        # extensión de la Excepción 1 del OBSERVATION_PERIOD.md.
        sentinel_agg: dict[str, dict] = {}  # sid → {weighted_sharpe_sum, total_trades}
        for score in scores:
            sid    = str(score["sentinel_id"])
            sharpe = max(float(score["sharpe_ratio"] or 0.0), 0.0)
            trades = int(score["total_trades"] or 0)

            if sid not in sentinel_agg:
                sentinel_agg[sid] = {"weighted_sharpe_sum": 0.0, "total_trades": 0}

            sentinel_agg[sid]["weighted_sharpe_sum"] += sharpe * trades
            sentinel_agg[sid]["total_trades"]        += trades

        # Calcular Sharpe agregado por sentinel
        sentinel_sharpes: dict[str, float] = {}
        for sid, agg in sentinel_agg.items():
            if agg["total_trades"] > 0:
                sentinel_sharpes[sid] = agg["weighted_sharpe_sum"] / agg["total_trades"]
            else:
                sentinel_sharpes[sid] = 0.0

        logger.debug(
            f"Sharpe agregado por sentinel: "
            f"{ {k: f'{v:.4f}' for k, v in sentinel_sharpes.items()} }"
        )

        # --- Paso 2: Half-Kelly allocation con Sharpes agregados ---
        total_sharpe = sum(sentinel_sharpes.values())
        allocation: dict[str, float] = {}

        for sid, sharpe in sentinel_sharpes.items():
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

    # ════════════════════════════════════════════════════════
    # § 5 — Pipeline de señal
    # ════════════════════════════════════════════════════════

    async def process_signal(
        self,
        sentinel_id: UUID,
        owner_id: UUID,
        ticker: str,
        signal_type: str,
        price: Decimal,
        qty: Decimal,
        strategy_type: str = "",
        ear_state: dict = None,
        allocation: dict = None,
        account_equity: Decimal = None,
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
        # Montos monetarios → Decimal en todo el pipeline (#H-4). Conversión defensiva
        # (acepta callers que aún pasen float durante la migración gradual).
        price = Decimal(str(price))
        qty = Decimal(str(qty))
        if account_equity is not None:
            account_equity = Decimal(str(account_equity))

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
                account_equity = await asyncio.wait_for(
                    asyncio.to_thread(self._get_account_equity),
                    timeout=15.0,
                )
            except asyncio.TimeoutError:
                logger.error("Timeout (15s) al obtener equity de cuenta")
                account_equity = Decimal("0")
            except Exception as e:
                logger.error(f"Error al obtener equity de cuenta: {e}")
                account_equity = Decimal("0")

        if account_equity > 0 and price > 0:
            max_dollar_value = account_equity * Decimal(str(sentinel_alloc / 100.0))
            max_qty          = max_dollar_value / price
            qty              = min(qty, max_qty)

        # 5. CorrelationGuard
        try:
            scores = await self.historian.get_sentinel_scores(owner_id)
        except Exception as e:
            logger.error(f"Error al obtener scores para CorrelationGuard: {e}")
            scores = []

        try:
            # CorrelationGuard espera list[dict] — convertir desde nuestro dict.
            guard_result = await self.correlation_guard.evaluate_signal(
                incoming_ticker    = ticker,
                incoming_qty       = qty,
                open_positions     = list(self.open_positions.values()),
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
        # Descartar BUY si ya hay posición abierta del mismo ticker en este cycle (#H-5).
        # Sin esto, dos sentinels emitiendo BUY del mismo ticker en el mismo cycle
        # generan doble-compra — el CorrelationGuard solo reduce qty, no descarta.
        if side == "BUY" and ticker in self.open_positions:
            logger.info(f"Señal BUY {ticker} omitida — ya hay posición abierta este cycle.")
            return {**base_result, "reason": "duplicate_ticker_buy"}
        if side == "SELL":
            if ticker not in self.open_positions:
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
                order_id     = order_result.get("order_id"),  # para reconciliación post-fill (#H-6)
            )
        except Exception as e:
            logger.error(f"Error al persistir señal/trade en Historian: {e}")
            signal_id = None
            trade_id  = None

        # Actualizar el cache local de posiciones según el resultado del fill (#H-5b).
        self._apply_fill_to_cache(
            ticker,
            order_result.get("status"),
            {"ticker": ticker, "qty": final_qty, "side": side, "sentinel_id": sentinel_id},
        )

        # PENDING (limit orders en background, FIX #H-6) NO se cuenta como aprobada
        # hasta que el background task confirme FILLED via update_trade_status.
        approved = order_result.get("status") == "FILLED"
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

    def _apply_fill_to_cache(self, ticker: str, status: str, position: dict) -> None:
        """Sincroniza el cache `open_positions` tras un fill (#H-5b).

        En un SELL FILLED la posición se cierra en Alpaca, así que debe REMOVERSE
        del cache. Antes se sobreescribía con side='SELL', dejando entradas fantasma
        que el sync con Alpaca marcaba como desincronización y que habilitaban shorts
        accidentales (incidentes SPY 11-may y QQQ 15-may; 45 warnings 18-22 may
        confirmaron que el bug era crónico). Solo un fill confirmado muta el cache.

        Args:
            ticker: símbolo operado.
            status: estado del fill que devolvió Alpaca; solo "FILLED" muta el cache.
            position: payload a cachear en un BUY ({ticker, qty, side, sentinel_id}).
        """
        if status != "FILLED":
            return
        if position["side"] == "SELL":
            self.open_positions.pop(ticker, None)
        else:
            self.open_positions[ticker] = position

    # ════════════════════════════════════════════════════════
    # § 6 — Ejecución de órdenes
    # ════════════════════════════════════════════════════════

    @staticmethod
    def _is_limit_strategy(strategy_type: str) -> bool:
        return strategy_type.lower() in _LIMIT_STRATEGIES

    async def execute_order(
        self,
        ticker: str,
        side: str,
        qty: Decimal,
        strategy_type: str = "",
        limit_price: Decimal = None,
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
        # Montos monetarios → Decimal (#H-4). Conversión defensiva (callers float ok).
        qty = Decimal(str(qty))
        if limit_price is not None:
            limit_price = Decimal(str(limit_price))

        is_limit = self._is_limit_strategy(strategy_type) and limit_price is not None

        original_qty = qty
        qty = int(math.floor(qty))
        if qty < 1:
            logger.info(
                f"Qty {original_qty:.4f} redondeada a 0 para {ticker} {side} — orden cancelada."
            )
            return {"order_id": None, "filled_price": None, "status": "CANCELLED"}

        try:
            submit_result = await asyncio.wait_for(
                asyncio.to_thread(
                    self._submit_order_sync, ticker, side, qty, strategy_type, limit_price
                ),
                timeout=15.0,
            )
        except asyncio.TimeoutError:
            logger.error(f"Timeout (15s) al enviar orden {ticker} {side} qty={qty}")
            return {"order_id": None, "filled_price": None, "status": "CANCELLED"}
        except Exception as e:
            logger.error(f"Alpaca rechazó la orden {ticker} {side} qty={qty}: {e}")
            return {"order_id": None, "filled_price": None, "status": "CANCELLED"}

        if not is_limit:
            return submit_result

        order_id = submit_result.get("order_id")
        if not order_id:
            # Submit falló o devolvió None → no hay nada que verificar después
            return submit_result

        # Lanzar verificación en background — no bloquear el cycle (#H-6).
        # Antes esto era `await asyncio.sleep(60)` síncrono, lo cual retrasaba
        # el procesamiento del resto de las señales del cycle.
        # TODO: reconciliación post-restart (sesiones futuras) — si el sistema
        # cae con tasks pendientes, las órdenes en Alpaca quedan activas pero
        # el sistema no las rastrea al restart. Requiere persistir tasks en DB.
        async def _check_later(oid: str):
            await asyncio.sleep(60)
            try:
                final = await asyncio.wait_for(
                    asyncio.to_thread(self._check_and_cancel_limit_sync, oid),
                    timeout=15.0,
                )
                # Reconciliar el trade en DB usando order_id (col agregada en migración 003)
                try:
                    await self.historian.update_trade_status(
                        order_id=oid,
                        status=final.get("status", "CANCELLED"),
                        filled_price=final.get("filled_price"),
                    )
                except Exception as e:
                    logger.error(f"Error actualizando trade order_id={oid} en DB: {e}")
            except asyncio.TimeoutError:
                logger.error(f"Timeout (15s) verificando limit {oid}")
            except Exception as e:
                logger.error(f"Limit check {oid}: {e}")

        logger.info(f"Limit order {order_id} enviada — verificación agendada en 60s (background).")
        asyncio.create_task(_check_later(order_id), name=f"limit_check_{order_id}")
        return submit_result   # devuelve PENDING inmediatamente — no bloquea el cycle

    def _submit_order_sync(
        self,
        ticker: str,
        side: str,
        qty: Decimal,
        strategy_type: str,
        limit_price: Decimal,
    ) -> dict:
        """Construye y envía la orden. Ejecutado en thread separado."""
        # Montos monetarios → Decimal (#H-4). Conversión defensiva.
        qty = Decimal(str(qty))
        if limit_price is not None:
            limit_price = Decimal(str(limit_price))

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

        filled_price = Decimal(str(order.filled_avg_price)) if order.filled_avg_price else None
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
                "filled_price": Decimal(str(order.filled_avg_price)) if order.filled_avg_price else None,
                "status":       "FILLED",
            }

        try:
            client.cancel_order_by_id(order_id)
            logger.info(f"Limit order {order_id} cancelada por timeout (60s sin fill).")
        except Exception as e:
            logger.warning(f"Error al cancelar limit order {order_id}: {e}")

        return {"order_id": order_id, "filled_price": None, "status": "CANCELLED"}

    def _get_account_equity(self) -> Decimal:
        """Retorna equity de la cuenta paper. Ejecutado en thread separado."""
        from alpaca.trading.client import TradingClient

        client  = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)
        account = client.get_account()
        return Decimal(str(account.equity))

    # ════════════════════════════════════════════════════════
    # § 7 — Kill switch
    # ════════════════════════════════════════════════════════

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
            await asyncio.wait_for(
                asyncio.to_thread(self._close_all_sync),
                timeout=15.0,
            )
        except asyncio.TimeoutError:
            logger.critical("Timeout (15s) durante liquidación del kill switch — verificar Alpaca manualmente")
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

    # ════════════════════════════════════════════════════════
    # § 8 — Ciclo principal
    # ════════════════════════════════════════════════════════

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
                cycle_equity = await asyncio.wait_for(
                    asyncio.to_thread(self._get_account_equity),
                    timeout=15.0,
                )
            except asyncio.TimeoutError:
                logger.error("Timeout (15s) obteniendo equity en run_cycle")
                cycle_equity = 0.0
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
