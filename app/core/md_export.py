"""Export přepisu jako Markdown — připravený jako prompt pro AI agenta.

Soubor je naformatovaný tak, aby ho student mohla rovnou vložit do
ChatGPT / Claude / Gemini chatu a měla z toho užitek bez další úpravy.

Obsahuje:
- YAML frontmatter s metadaty
- "Co s tímhle můžeš dělat" sekci adaptovanou na konkrétní AI
- Plný přepis se značkami času
- Sekci se slidy (pokud existují)
- Návrh follow-up promptů
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from loguru import logger

from app.core.models import SlideText, Transcript

# Custom instrukce pro různé AI služby — tady přidáváme přidanou hodnotu
# pokud uživatel řekne, jakou AI používá. Pro 'none' je generic.
_AI_INSTRUCTIONS: dict[str, str] = {
    "none": (
        "## Jak tohle používat\n\n"
        "Tento soubor obsahuje plný přepis přednášky. Můžeš ho nahrát do\n"
        "ChatGPT, Claude, Gemini, nebo jakékoli AI a zeptat se třeba:\n"
        "- Shrň hlavní body této přednášky\n"
        "- Vysvětli mi koncept X (cituj časovou značku)\n"
        "- Vytvoř mi kvíz na opakování\n"
        "- Co jsem si měl/a zapamatovat ke zkoušce?\n"
    ),
    "chatgpt": (
        "## Jak používat s ChatGPT Plus\n\n"
        "1. **Nový chat** → klikni 📎 → nahraj tento soubor\n"
        "2. Pošli: *Toto je přepis přednášky. Vytvoř studijní materiál — "
        "hlavní body, definice pojmů, otázky ke zkoušce.*\n"
        "3. **Tip:** vytvoř si **Project** pro tento předmět a tam nahrávej všechny přepisy.\n"
        "   Pak ChatGPT zná kontext celého semestru.\n"
        "4. **Code Interpreter:** *Vygeneruj flashcards v Anki formátu z tohoto přepisu*\n"
    ),
    "claude": (
        "## Jak používat s Claude Pro\n\n"
        "1. **Nový chat** → klikni 📎 → nahraj tento soubor (Claude přijme až 5 souborů)\n"
        "2. Pošli: *Toto je přepis vysokoškolské přednášky. "
        "Vytvoř mi strukturovaný studijní materiál — hlavní body, definice, příklady, otázky.*\n"
        "3. **Tip:** vytvoř si **Project** pro daný předmět. Můžeš tam nahrát všechny přepisy "
        "ze semestru + svoje poznámky + sylabu. Claude pak má všechen kontext najednou.\n"
        "4. **Artifacts:** *Vytvoř HTML stránku se shrnutím a interaktivním kvízem.*\n"
    ),
    "gemini": (
        "## Jak používat s Gemini Advanced\n\n"
        "1. Otevři **gemini.google.com** → nový chat → klikni 📎 → nahraj soubor\n"
        "2. Pošli: *Toto je přepis přednášky. Vytvoř studijní materiál a navrhni otázky.*\n"
        "3. **Tip:** Gemini umí Google Workspace integraci — můžeš požádat o "
        "export shrnutí do Google Docs nebo Sheets.\n"
        "4. **Deep Research:** *Najdi další zdroje na toto téma a porovnej je s přepisem.*\n"
    ),
    "other": (
        "## Jak používat s tvou AI\n\n"
        "Nahraj tento .md soubor do své AI a zkus tyto prompty:\n"
        "- *Shrň hlavní body této přednášky*\n"
        "- *Vytvoř mi studijní materiál: pojmy + definice + příklady*\n"
        "- *Navrhni otázky které by mohly být ke zkoušce*\n"
        "- *Vysvětli mi koncept X (čas mm:ss) jednodušším způsobem*\n"
    ),
}

_FOLLOWUP_PROMPTS: list[str] = [
    "Shrň mi hlavní body této přednášky v 10 odrážkách.",
    "Vytvoř mi studijní materiál: pojmy + definice + příklady.",
    "Navrhni 10 otázek které by mohly být u zkoušky.",
    "Vysvětli mi koncept [doplň pojem] jednodušším způsobem.",
    "Najdi v přepisu místa kde řečník zmiňuje [téma].",
    "Vytvoř flashcards (otázka → odpověď) pro opakování.",
    "Sestav mi mind-map hlavních témat.",
]


def export_markdown(
    *,
    output_path: Path,
    transcripts: list[Transcript],
    slides: list[SlideText] | None = None,
    user_prompt: str | None = None,
    ai_service: str = "none",
    whisper_model: str = "medium",
) -> Path:
    """Vytvoří .md soubor připravený jako prompt pro AI.

    `ai_service` = none | chatgpt | claude | gemini | other
    """
    slides = slides or []
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total_seconds = sum(t.duration_sec for t in transcripts) if transcripts else 0
    total_words = sum(len(t.text.split()) for t in transcripts) if transcripts else 0

    lines: list[str] = []

    # ----- YAML frontmatter -----
    lines.append("---")
    lines.append(f"datum_prepisu: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"delka_nahravky_minut: {total_seconds / 60:.1f}")
    lines.append(f"pocet_slov_v_prepisu: {total_words}")
    lines.append(f"whisper_model: {whisper_model}")
    lines.append("jazyk: cs")
    if user_prompt:
        # Escape pro YAML
        safe = user_prompt.replace('"', '\\"').replace("\n", " ")
        lines.append(f'popis_studenta: "{safe}"')
    lines.append("---")
    lines.append("")

    # ----- Titulek -----
    title = "Přepis přednášky"
    if transcripts and len(transcripts) == 1:
        title = f"Přepis: {transcripts[0].source_label}"
    elif transcripts:
        title = f"Přepis z {len(transcripts)} nahrávek"
    lines.append(f"# {title}")
    lines.append("")

    # ----- AI instrukce -----
    ai_instr = _AI_INSTRUCTIONS.get(ai_service, _AI_INSTRUCTIONS["none"])
    lines.append(ai_instr)
    lines.append("")

    # ----- Popis od studenta (pokud zadal) -----
    if user_prompt:
        lines.append("## Kontext od studenta")
        lines.append("")
        lines.append("> " + user_prompt.strip().replace("\n", "\n> "))
        lines.append("")

    # ----- Přepis -----
    lines.append("## Plný přepis přednášky")
    lines.append("")
    for tr in transcripts:
        lines.append(f"### {tr.source_label}")
        duration_str = _format_seconds(tr.duration_sec)
        lines.append(f"*Délka: {duration_str}, {len(tr.text.split())} slov*")
        lines.append("")
        if tr.segments:
            last_marker_minute = -1
            current_paragraph: list[str] = []
            for seg in tr.segments:
                # Nová značka času každou plnou minutu (00:30 → 01:00 → 02:00)
                minute = int(seg.start // 60)
                if minute > last_marker_minute:
                    if current_paragraph:
                        lines.append(" ".join(current_paragraph))
                        lines.append("")
                        current_paragraph = []
                    lines.append(f"**[{_format_seconds(seg.start)}]**")
                    last_marker_minute = minute
                current_paragraph.append(seg.text.strip())
            if current_paragraph:
                lines.append(" ".join(current_paragraph))
        else:
            # Žádné segmenty s časem — jen plný text
            lines.append(tr.text)
        lines.append("")

    # ----- Slidy -----
    if any(sl.text for sl in slides):
        lines.append("## Obsah prezentací")
        lines.append("")
        for sl in slides:
            if not sl.text:
                continue
            lines.append(f"### {sl.source_label}")
            lines.append(f"*{sl.slide_count} slidů*")
            lines.append("")
            for block in sl.text.split("\n\n"):
                if block.strip():
                    lines.append(block.strip())
                    lines.append("")

    # ----- Followup prompts -----
    lines.append("---")
    lines.append("")
    lines.append("## Návrhy promptů pro AI")
    lines.append("")
    lines.append("Zkopíruj kterýkoli z nich do chatu:")
    lines.append("")
    for prompt in _FOLLOWUP_PROMPTS:
        lines.append(f"- {prompt}")
    lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info(
        "Uloženo .md: {} ({:.1f} KB, AI služba: {})",
        output_path,
        output_path.stat().st_size / 1024,
        ai_service,
    )
    return output_path


def _format_seconds(seconds: float) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"
