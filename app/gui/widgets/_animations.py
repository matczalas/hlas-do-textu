"""Animation helpers — sdílené Qt animace pro hover, fade, slide.

Qt QSS neumí CSS transitions, takže pro plynulé efekty (translateY, fade,
slide indikátoru) musíme použít QPropertyAnimation. Tady jsou utility, které
to balí do reusable patternů.

Použití:
    from app.gui.widgets._animations import attach_lift_effect

    card = QPushButton(...)
    attach_lift_effect(card)   # hover → zvedne se o 2px + stín

API:
    attach_lift_effect(widget, lift=2, blur=22, duration=150)
        — hover lift přes QGraphicsDropShadowEffect a translate.
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPropertyAnimation,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QWidget

from app.gui.styles import tokens


class _LiftFilter(QObject):
    """Event filter — chytá enter/leave na target widgetu a animuje lift + stín."""

    def __init__(
        self,
        target: QWidget,
        lift: int = 2,
        blur: int = 22,
        duration_ms: int = 0,
    ) -> None:
        super().__init__(target)
        self._target = target
        self._lift = lift
        self._duration = duration_ms or tokens.DUR_MICRO

        # Drop shadow effect — defaultně disabled, enable při hover
        self._shadow = QGraphicsDropShadowEffect(target)
        self._shadow.setBlurRadius(blur)
        self._shadow.setOffset(0, 8)
        # Shadow color: rgba(10, 22, 40, 26) ≈ 10% black-deep
        self._shadow.setColor(QColor(10, 22, 40, 26))
        self._shadow.setEnabled(False)
        target.setGraphicsEffect(self._shadow)

        # Animation pro geometry (kvůli translateY)
        self._anim: QPropertyAnimation | None = None
        self._original_y: int | None = None

        target.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is not self._target:
            return False
        et = event.type()
        if et == QEvent.Type.Enter:
            self._on_enter()
        elif et == QEvent.Type.Leave:
            self._on_leave()
        return False  # nikdy nezachycuj event, jen pozoruj

    def _on_enter(self) -> None:
        self._shadow.setEnabled(True)
        geo = self._target.geometry()
        if self._original_y is None:
            self._original_y = geo.y()
        target_geo = geo.translated(0, -self._lift)
        self._animate_to(target_geo)

    def _on_leave(self) -> None:
        self._shadow.setEnabled(False)
        if self._original_y is None:
            return
        geo = self._target.geometry()
        target_geo = geo
        target_geo.moveTop(self._original_y)
        self._animate_to(target_geo)

    def _animate_to(self, target_geometry) -> None:
        if self._anim is not None and self._anim.state() == QPropertyAnimation.State.Running:
            self._anim.stop()
        self._anim = QPropertyAnimation(self._target, b"geometry", self._target)
        self._anim.setDuration(self._duration)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.setStartValue(self._target.geometry())
        self._anim.setEndValue(target_geometry)
        self._anim.start()


def attach_lift_effect(
    widget: QWidget,
    *,
    lift: int = 2,
    blur: int = 22,
    duration_ms: int = 0,
) -> _LiftFilter:
    """Připojí hover lift + drop shadow na widget. Vrací filter (drží referenci).

    Args:
        widget: target widget (musí být v layoutu, ne plovoucí)
        lift: o kolik pixelů zvednout při hover (default 2)
        blur: blur radius stínu (default 22)
        duration_ms: trvání animace (default tokens.DUR_MICRO = 150ms)

    Returns:
        Filter instance (parent je widget, ale držet referenci pomáhá GC).
    """
    return _LiftFilter(widget, lift=lift, blur=blur, duration_ms=duration_ms)
