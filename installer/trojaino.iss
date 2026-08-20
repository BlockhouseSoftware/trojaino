; Conventional per-user Windows installer for the standalone tjscan bundle.
; Build with ISCC and define SourceDir, OutputDir, and AppVersion.

#ifndef SourceDir
  #define SourceDir "..\dist\tjscan"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist\installer"
#endif
#ifndef AppVersion
  #define AppVersion "0.1.4"
#endif

#define AppName "Trojaino"
#define AppPublisher "Blockhouse Software"
#define AppExecutable "tjscan.exe"

[Setup]
AppId={{0B0A8371-D71C-4591-B184-6D5D203A302D}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\Trojaino
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir={#OutputDir}
OutputBaseFilename=Trojaino-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#AppExecutable}
ChangesEnvironment=yes

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Code]
function NormalizedPath(Value: string): string;
begin
  Result := Lowercase(RemoveBackslashUnlessRoot(Trim(Value)));
end;

function UserPathContains(Directory: string): Boolean;
var
  ExistingPath: string;
  Entries: TArrayOfString;
  Index: Integer;
begin
  Result := False;
  if not RegQueryStringValue(HKCU, 'Environment', 'Path', ExistingPath) then
    Exit;

  Entries := StringSplit(ExistingPath, [';'], stExcludeEmpty);
  for Index := 0 to GetArrayLength(Entries) - 1 do
  begin
    if NormalizedPath(Entries[Index]) = NormalizedPath(Directory) then
    begin
      Result := True;
      Exit;
    end;
  end;
end;

procedure AddToUserPath(Directory: string);
var
  ExistingPath: string;
begin
  if UserPathContains(Directory) then
    Exit;

  if not RegQueryStringValue(HKCU, 'Environment', 'Path', ExistingPath) then
    ExistingPath := '';
  if (ExistingPath <> '') and (ExistingPath[Length(ExistingPath)] <> ';') then
    ExistingPath := ExistingPath + ';';
  RegWriteExpandStringValue(HKCU, 'Environment', 'Path', ExistingPath + Directory);
end;

procedure RemoveFromUserPath(Directory: string);
var
  ExistingPath: string;
  Entries: TArrayOfString;
  Index: Integer;
  RebuiltPath: string;
begin
  if not RegQueryStringValue(HKCU, 'Environment', 'Path', ExistingPath) then
    Exit;

  Entries := StringSplit(ExistingPath, [';'], stExcludeEmpty);
  RebuiltPath := '';
  for Index := 0 to GetArrayLength(Entries) - 1 do
  begin
    if (Entries[Index] <> '') and (NormalizedPath(Entries[Index]) <> NormalizedPath(Directory)) then
    begin
      if RebuiltPath <> '' then
        RebuiltPath := RebuiltPath + ';';
      RebuiltPath := RebuiltPath + Entries[Index];
    end;
  end;
  RegWriteExpandStringValue(HKCU, 'Environment', 'Path', RebuiltPath);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    AddToUserPath(ExpandConstant('{app}'));
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RemoveFromUserPath(ExpandConstant('{app}'));
end;
