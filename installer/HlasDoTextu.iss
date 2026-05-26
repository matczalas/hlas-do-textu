; Inno Setup script pro Hlas do textu
; Generuje HlasDoTextu-Setup-<version>.exe v Output/
; Sestavovat pomocí ISCC v CI runneru.

#define MyAppName "Hlas do textu"
#define MyAppVersion "0.3.0"
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
; UNINSTALL — dotaz na smazání user dat (modely, config, logy, klíč v keyring)
; ---------------------------------------------------------------------------

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  UserDataDir: string;
  MsgResult: Integer;
  ResultCode: Integer;
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

        // Smazat uložený Gemini API klíč z Windows Credential Manager.
        // Selhání ignorujeme (klíč třeba neexistuje).
        Exec(ExpandConstant('{cmd}'), '/C cmdkey /delete:HlasDoTextu.gemini',
             '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
      end;
    end
    else
    begin
      // Pro jistotu zkusit smazat keyring entry i bez user-data dir
      Exec(ExpandConstant('{cmd}'), '/C cmdkey /delete:HlasDoTextu.gemini',
           '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    end;
  end;
end;
