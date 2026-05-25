# Jak získat Gemini API klíč zdarma

Trvá to cca 2 minuty. Potřebuješ jen Google účet (gmail).

## Nejrychlejší cesta (z aplikace)

1. V uvítacím dialogu nebo v **Nastavení** klikni na tlačítko **🔗 Získat API klíč zdarma**.
2. Otevře se ti tvůj prohlížeč přímo na [stránce s API klíči](https://aistudio.google.com/api-keys).
3. Přihlas se Google účtem (pokud nejsi).
4. Klikni na **"Create API key"** → vyber/vytvoř projekt → klíč se vygeneruje.
5. **Zkopíruj klíč** tlačítkem Copy.
6. Vrať se do aplikace a vlož klíč do pole.

## Postup ručně (kdyby tlačítko nefungovalo)

1. Otevři [https://aistudio.google.com/api-keys](https://aistudio.google.com/api-keys) v prohlížeči.
2. Přihlas se svým Google účtem.
3. Klikni na **"Create API key"**.
4. Vyber projekt (pokud žádný nemáš, AI Studio nabídne vytvořit nový — stačí kliknout Create).
5. Klíč vypadá takhle: `AIzaSyXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` (asi 40 znaků).
6. **Zkopíruj klíč** (tlačítko Copy vedle něj).

## Vlož klíč do aplikace

1. Otevři **Hlas do textu**.
2. Klikni **⚙ Nastavení** (vpravo dole).
3. Vlož klíč do políčka **"Gemini API klíč"**.
4. Zaškrtni souhlas s odesíláním textu do Gemini.
5. Klikni **OK**.

Klíč se uloží bezpečně do Windows Credential Manager — není v žádném textovém souboru.

## Free tier limity (k 2026)

- **15 dotazů za minutu** (víc než stačí — aplikace stejně neposílá víc než 4 paralelní)
- **1 500 dotazů za den** (vystačí na ~50 hodinových přednášek denně)
- **1 milion tokenů kontextu** (celá přednáška se vejde najednou)

## Co když se mi klíč ztratí?

1. Vrať se na [aistudio.google.com → Get API key](https://aistudio.google.com).
2. Můžeš si vytvořit nový klíč (max 4 klíče na účet).
3. Starý klíč můžeš smazat (klikni na 3 tečky vedle něj).

## Soukromí

Google v free tieru **používá texty dotazů k tréninku modelů**. Pro běžné školní materiály to není problém, ale pro citlivý obsah (interní výzkum, lékařské záznamy apod.) raději použij offline Ollama variantu — viz [INSTALACE_OLLAMA.md](INSTALACE_OLLAMA.md).

Plný text podmínek: https://ai.google.dev/gemini-api/terms
