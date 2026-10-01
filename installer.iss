; Installeur Inno Setup. Construire l'exe d'abord (build.ps1), puis :
;   iscc /DAppVersion=0.4.0 installer.iss
; Le résultat est dist\gazefocus-setup.exe.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{B6E0B0C4-6C7B-4E55-9C0E-2B1F6A5D9E31}
AppName=gazefocus
AppVersion={#AppVersion}
AppPublisher=Mat8313
AppPublisherURL=https://github.com/Mat8313/gazefocus
; Installation par utilisateur : aucun droit administrateur demandé.
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\gazefocus
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\gazefocus.exe
OutputDir=dist
OutputBaseFilename=gazefocus-setup
Compression=lzma2
SolidCompression=yes
; Même nom que le mutex créé par l'app : l'installeur demande de la fermer
; si elle tourne, au lieu d'échouer sur des fichiers verrouillés.
AppMutex=gazefocus-single-instance

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Files]
Source: "dist\gazefocus\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\gazefocus"; Filename: "{app}\gazefocus.exe"

[Run]
Filename: "{app}\gazefocus.exe"; Description: "Lancer gazefocus"; Flags: nowait postinstall skipifsilent

[Registry]
; Retire le lancement au démarrage (activé depuis le menu de l'app) à la désinstallation.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "gazefocus"; Flags: dontcreatekey uninsdeletevalue
