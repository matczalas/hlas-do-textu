; Inno Setup script pro Hlas do textu
; Generuje HlasDoTextu-Setup-<version>.exe v Output/
; Sestavovat pomocí ISCC v CI runneru.

#define MyAppName "Hlas do textu"
#define MyAppVersion "1.4.2"
#define MyAppPublisher "Safe4Future z. u."
#define MyAppExeName "HlasDoTextu.exe"
#define MyAppId "{{C0FE4F50-AF60-4F7E-8C0F-2A5B0E0E6F7A}}"
#define UserDataDir "{localappdata}\HlasDoTextu"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
; Instalační adresář oddělený od user-data adresáře, aby uninstall nemazal modely bez svolení.
DefaultDirName={localappdata}\Programs\HlasDoTextu
DefaultGroupName=Hlas do textu
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=Output
OutputBaseFilename=HlasDoTextu-Setup-{#MyAppVersion}
SetupIconFile=..\app\resources\icon.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
LicenseFile=LICENSE_cs.txt
LanguageDetectionMethod=uilanguage
; AppMutex — když aplikace běží, Inno Setup (instalace i odinstalace) počká /
; vyzve uživatele k jejímu zavření, místo aby narazil na zamčený .exe nebo
; zamčené logy. Aplikace musí stejnojmenný mutex vytvořit při startu
; (viz app/__main__.py).
AppMutex=Global\HlasDoTextu_Running_Mutex
; CloseApplications — při upgradu Inno Setup automaticky zavře běžící
; instanci a po instalaci ji volitelně restartuje. Řeší race s uvolněním .exe.
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "czech"; MessagesFile: "compiler:Languages\Czech.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; Bere se výstup z PyInstaller --onedir
Source: "..\dist\HlasDoTextu\HlasDoTextu.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\HlasDoTextu\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Start menu + plocha + odinstalátor — všechny ikony se vytvoří vždy.
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Odinstalovat {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Comment: "Hlas do textu — přepis a body z přednášek"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Spustit Hlas do textu"; Flags: nowait postinstall skipifsilent

; ---------------------------------------------------------------------------
; CODE — vlastní stránky a uninstall handlery
; ---------------------------------------------------------------------------

[Code]

// Druhá stránka po wpLicense — uživatel musí explicitně potvrdit, že si
// licenci přečetl. Brání bezmyšlenkovému prokliknutí standardního Next.
var
  ConfirmPage: TInputOptionWizardPage;

procedure InitializeWizard();
begin
  ConfirmPage := CreateInputOptionPage(
    wpLicense,
    'Potvrzení licence',
    'Ujisti se, že jsi licenční podmínky skutečně přečetl',
    'Aplikace Hlas do textu je placený nástroj se závaznými pravidly použití.' + #13#10 +
    'Body licence mohou ovlivnit odpovědnost, sdílení dat i obchodní použití.' + #13#10 + #13#10 +
    'Označením potvrzuješ, že jsi licenci na předchozí stránce přečetl a souhlasíš s ní.' + #13#10 +
    'Bez tohoto potvrzení nelze pokračovat.',
    True, False);
  ConfirmPage.Add('Potvrzuji, že jsem si přečetl licenční podmínky a souhlasím s nimi.');
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (ConfirmPage <> nil) and (CurPageID = ConfirmPage.ID) then
  begin
    if not ConfirmPage.Values[0] then
    begin
      MsgBox(
        'Pro pokračování označ, že jsi licenci přečetl a souhlasíš s ní.',
        mbError, MB_OK);
      Result := False;
    end;
  end;
end;

// ---------------------------------------------------------------------------
// UNINSTALL — dotaz na smazání user dat (modely, config, logy, klíč v keyring)
// ---------------------------------------------------------------------------

procedure DeleteStoredCredentials();
var
  ResultCode: Integer;
begin
  // Python `keyring` (WinVaultKeyring) ukládá credentials pod target name
  // ve formátu "<service>@<username>". Aplikace používá:
  //   - HlasDoTextu.gemini  / default   → Gemini API klíč
  //   - HlasDoTextu.license / default   → licenční klíč
  // Mažeme oba ve formátu "@default" i bez, ať to projde napříč verzemi
  // keyring knihovny. Selhání (klíč neexistuje) ignorujeme.
  Exec(ExpandConstant('{cmd}'), '/C cmdkey /delete:HlasDoTextu.gemini@default',
       '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{cmd}'), '/C cmdkey /delete:HlasDoTextu.license@default',
       '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{cmd}'), '/C cmdkey /delete:HlasDoTextu.gemini',
       '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{cmd}'), '/C cmdkey /delete:HlasDoTextu.license',
       '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  UserDataDir: string;
  MsgResult: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    UserDataDir := ExpandConstant('{#UserDataDir}');

    // Zeptat se uživatele na smazání modelů + nastavení.
    // Default Yes — kamarádka tím uvolní cca 1 GB v AppData.
    if DirExists(UserDataDir) then
    begin
      MsgResult := MsgBox(
        'Smazat také tvoje stažené Whisper modely a nastavení?' + #13#10 + #13#10 +
        'Modely jsou v: ' + UserDataDir + #13#10 +
        '(typicky 0.5 - 1.5 GB).' + #13#10 + #13#10 +
        'ANO = úplné odinstalování, nic po aplikaci nezbyde (doporučeno).' + #13#10 +
        'NE = ponechat modely a nastavení pro případnou pozdější instalaci.',
        mbConfirmation, MB_YESNO);

      if MsgResult = IDYES then
      begin
        DelTree(UserDataDir, True, True, True);
        DeleteStoredCredentials();
      end;
    end
    else
    begin
      // I bez user-data dir zkusíme smazat citlivé klíče z Credential Manageru
      DeleteStoredCredentials();
    end;
  end;
end;
