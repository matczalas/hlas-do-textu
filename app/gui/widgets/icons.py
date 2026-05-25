"""SVG ikony renderované přes QSvgRenderer.

Žádné externí závislosti — SVG je inline string, který se barví podle aktuální
palette() role textu. Vrací buď QIcon nebo QPixmap.

Použití:
    from app.gui.widgets.icons import icon, pixmap
    btn.setIcon(icon("mic", size=18))
    label.setPixmap(pixmap("sparkles", size=24, color="#205ca8"))
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

# Stroke ikony — viewBox 24×24, stroke-width 1.75, kulaté konce.
# {stroke} je nahrazen barvou v runtime.
_SVG: dict[str, str] = {
    "mic": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
            stroke="{stroke}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
            <rect x="9" y="3" width="6" height="11" rx="3"/>
            <path d="M6 11a6 6 0 0 0 12 0"/>
            <path d="M12 17v4"/><path d="M9 21h6"/></svg>""",
    "slides": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
            stroke="{stroke}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="4" width="18" height="14" rx="2"/>
            <path d="M3 9h18"/><path d="M8 22l4-3 4 3"/></svg>""",
    "upload": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
            stroke="{stroke}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 17V3"/><path d="M6 9l6-6 6 6"/>
            <path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/></svg>""",
    "sparkles": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
            stroke="{stroke}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 3l1.8 4.6L18.4 9.4 13.8 11.2 12 16l-1.8-4.8L5.6 9.4l4.6-1.8z"/>
            <path d="M19 14l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z"/>
            <path d="M5 17l.6 1.4 1.4.6-1.4.6-.6 1.4-.6-1.4-1.4-.6 1.4-.6z"/></svg>""",
    "settings": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
            stroke="{stroke}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="3"/>
            <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1.03 1.56V21a2 2 0 1 1-4 0v-.07a1.7 1.7 0 0 0-1.11-1.56 1.7 1.7 0 0 0-1.87.34l-.06.06A2 2 0 1 1 4.13 16.94l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.56-1.03H3a2 2 0 1 1 0-4h.07a1.7 1.7 0 0 0 1.56-1.11 1.7 1.7 0 0 0-.34-1.87l-.06-.06A2 2 0 1 1 7.06 4.13l.06.06a1.7 1.7 0 0 0 1.87.34H9a1.7 1.7 0 0 0 1.03-1.56V3a2 2 0 1 1 4 0v.07a1.7 1.7 0 0 0 1.03 1.56 1.7 1.7 0 0 0 1.87-.34l.06-.06A2 2 0 1 1 19.82 7.06l-.06.06a1.7 1.7 0 0 0-.34 1.87V9a1.7 1.7 0 0 0 1.56 1.03H21a2 2 0 1 1 0 4h-.07a1.7 1.7 0 0 0-1.56 1.03Z"/></svg>""",
    "folder": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
            stroke="{stroke}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 7a2 2 0 0 1 2-2h4l2 3h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>""",
    "trash": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
            stroke="{stroke}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
            <path d="M4 7h16"/><path d="M9 7V4h6v3"/>
            <path d="M6 7v13a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V7"/>
            <path d="M10 11v6"/><path d="M14 11v6"/></svg>""",
    "check": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
            stroke="{stroke}" stroke-width="2.25" stroke-linecap="round" stroke-linejoin="round">
            <path d="M5 12l4.5 4.5L19 7"/></svg>""",
    "x": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
            stroke="{stroke}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
            <path d="M6 6l12 12"/><path d="M18 6L6 18"/></svg>""",
    "external": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
            stroke="{stroke}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
            <path d="M10 5H5v14h14v-5"/><path d="M14 4h6v6"/><path d="M11 13L20 4"/></svg>""",
    "info": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
            stroke="{stroke}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><circle cx="12" cy="8" r="0.5" fill="{stroke}"/></svg>""",
    "key": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
            stroke="{stroke}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="8" cy="14" r="4"/>
            <path d="M11 11l9-9"/><path d="M16 6l3 3"/><path d="M18 4l3 3"/></svg>""",
    "eye": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
            stroke="{stroke}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
            <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/>
            <circle cx="12" cy="12" r="3"/></svg>""",
    "eye-off": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
            stroke="{stroke}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
            <path d="M4 4l16 16"/><path d="M10.6 6.2A9.6 9.6 0 0 1 12 6c6.5 0 10 7 10 7a16 16 0 0 1-3 4"/>
            <path d="M6 7A16 16 0 0 0 2 12s3.5 7 10 7c1.3 0 2.5-.2 3.6-.6"/>
            <path d="M10 10a3 3 0 0 0 4 4"/></svg>""",
    "graduation": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
            stroke="{stroke}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
            <path d="M2 9l10-5 10 5-10 5z"/><path d="M6 11v5c0 1.5 3 3 6 3s6-1.5 6-3v-5"/>
            <path d="M22 9v6"/></svg>""",
    "wand": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
            stroke="{stroke}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
            <path d="M15 4l5 5L9 20l-5-5z"/><path d="M14 5l5 5"/>
            <path d="M19 3l1 2 2 1-2 1-1 2-1-2-2-1 2-1z"/></svg>""",
    "document": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
            stroke="{stroke}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
            <path d="M7 3h7l5 5v12a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"/>
            <path d="M14 3v5h5"/><path d="M9 13h6"/><path d="M9 17h6"/></svg>""",
    "audio": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
            stroke="{stroke}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
            <path d="M4 10v4"/><path d="M8 7v10"/><path d="M12 4v16"/>
            <path d="M16 7v10"/><path d="M20 10v4"/></svg>""",
    "arrow-right": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
            stroke="{stroke}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
            <path d="M5 12h14"/><path d="M13 6l6 6-6 6"/></svg>""",
}


def _resolve_color(color: str | QColor | None) -> str:
    if color is None:
        app = QApplication.instance()
        if app is not None:
            return app.palette().color(QPalette.ColorRole.Text).name()
        return "#222222"
    if isinstance(color, QColor):
        return color.name()
    return color


def pixmap(name: str, size: int = 20, color: str | QColor | None = None) -> QPixmap:
    """Vykreslí ikonu jako QPixmap v dané velikosti a barvě."""
    svg = _SVG.get(name)
    if not svg:
        return QPixmap()
    stroke = _resolve_color(color)
    data = svg.replace("{stroke}", stroke).encode("utf-8")

    dpr = 2.0
    px = int(size * dpr)
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)

    renderer = QSvgRenderer(QByteArray(data))
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter, QRectF(0, 0, px, px))
    painter.end()

    pm.setDevicePixelRatio(dpr)
    return pm


def icon(name: str, size: int = 18, color: str | QColor | None = None) -> QIcon:
    """Vrátí QIcon pro tlačítka."""
    return QIcon(pixmap(name, size, color))


def icon_size(size: int = 18) -> QSize:
    return QSize(size, size)
