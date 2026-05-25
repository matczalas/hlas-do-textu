# Instalace Ollama (volitelný offline režim)

Ollama je program, který spustí AI **lokálně** na tvém PC — bez internetu, bez poplatků, bez odesílání dat do cloudu.

**Kdy se hodí:**
- Chceš pracovat offline (na cestách, ve škole bez wifi).
- Materiál obsahuje citlivé údaje, které nechceš posílat do cloudu.
- Vyčerpal jsi denní free tier Gemini.

**Kdy se nehodí:**
- Pokud máš PC se 4-8 GB RAM (Ollama potřebuje aspoň 8 GB volných, ideálně 16+).
- **Pokud chceš co nejvyšší kvalitu češtiny — cloudové modely jsou výrazně lepší.** Konkrétní porovnání viz níže.

## Realita: Ollama (8B model) vs. Gemini

Otestováno na 3-minutovém úryvku TEDx přednášky (Iva Pekárková, *„Neřest jménem cestování"*):

| Vlastnost | Gemini `flash-latest` | Ollama `llama3.2:3b` |
|---|---|---|
| **Čas zpracování** | 17 s | 43 s (2,5× pomalejší) |
| **Body** | 6 hutných | 4 nesourodých |
| **Pojmy s definicí** | 3 přesné | 2 prázdné názvy |
| **Příklady** | 2 konkrétní | 1 nedořečený |
| **Doporučení k učení** | 3 akademické otázky | 1 obecná věta |
| **Anglicismy v textu** | žádné | "because", "when" v české větě |
| **Gramatika** | bezchybná | občas chybné slovesné tvary |

**Závěr:** Ollama `llama3.2:3b` je **použitelný jako záloha** (lepší než nic), ale **nedosahuje kvality Gemini**. Pokud máš slušné PC (16+ GB RAM) a chceš vyšší kvalitu, zkus větší model `llama3.1:8b` (5 GB) — kvalita češtiny je výrazně lepší, ale generování trvá 2-3× déle.

## Instalace na Windows

1. Stáhni instalátor z https://ollama.com/download/windows.
2. Spusť **OllamaSetup.exe** a postupuj podle průvodce.
3. Po instalaci se Ollama spustí jako služba na pozadí — uvidíš ikonu v systray vpravo dole.

## Stáhni model pro češtinu

V příkazovém řádku (Win + R → `cmd` → Enter) zadej:

```
ollama pull llama3.2:3b
```

Stahování trvá 3-10 minut (model má ~2 GB).

Můžeš vyzkoušet i větší model pro lepší kvalitu (pokud máš 16+ GB RAM):

```
ollama pull llama3.1:8b
```

## Nastavení v aplikaci

1. Otevři **Hlas do textu**.
2. Status řádek dole by měl ukazovat **"Ollama: ✅ běží"**.
3. (Volitelně) v **Nastavení** zaškrtni **"Vždy používat lokální Ollama"** — aplikace pak nebude posílat nic do Gemini.

## Když to nefunguje

| Problém | Řešení |
|---|---|
| Status říká **"Ollama: ❌ neaktivní"** | Otevři Start → Ollama → spustí se služba. Nebo zkus restartovat PC. |
| **"model llama3.2:3b není stažený"** | Spusť `ollama pull llama3.2:3b` v cmd. |
| Aplikace běží **velmi pomalu** | Lokální AI je pomalejší než cloud. Hodinová přednáška = 5-15 minut generování bodů. |
| **Out of memory** | Tvůj PC nemá dost RAM. Zkus menší model: `ollama pull llama3.2:1b`. |

## Odinstalace

Stejně jako každou Windows aplikaci: Settings → Apps → Ollama → Uninstall.

Stažené modely zůstávají v `C:\Users\<jméno>\.ollama\models\` — pokud chceš uvolnit místo, smaž tuto složku.
