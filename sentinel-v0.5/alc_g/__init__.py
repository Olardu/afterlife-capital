# alc_g/ — Runtime mínimo de ALC-G Fase 0 (núcleo pasivo apalancado).
#
# Independiente del bot Sentinel: NO importa dispatcher/main/the_ear ni toca la
# cuenta de trading #1. Opera sobre una cuenta Alpaca paper SEPARADA (#2).
# Spec: teamwork/alc-g-phase0-runtime-spec.md (Deep handoff #105).
#
# GATE cerrado (Roman): 1.5× techo + slider humano + glide-path + piso $100K.
# Sin Sentinels, sin satélite, sin Universe Selector. Solo el core-blend 40/30/30.
