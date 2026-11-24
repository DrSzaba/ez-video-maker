; EZ Video Maker - per-user installer (no admin needed).
; Mirrors the 3.6.0 installer: same folder, shortcuts, registry and
; /S + /UPDATE handling used by the built-in updater.
Unicode true
SetCompressor /SOLID lzma

!define APPNAME "EZ Video Maker"
!define VERSION "3.8.0"
!define REGKEY  "Software\EZVideoMaker"
!define UNKEY   "Software\Microsoft\Windows\CurrentVersion\Uninstall\EZVideoMaker"

!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "LogicLib.nsh"

Name "${APPNAME}"
OutFile "EZ-Video-Maker-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\${APPNAME}"
InstallDirRegKey HKCU "${REGKEY}" "InstallDir"
RequestExecutionLevel user
BrandingText "${APPNAME} ${VERSION} - Dr. Szaba"
VIProductVersion "3.8.0.0"
VIAddVersionKey "ProductName" "${APPNAME}"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "ProductVersion" "${VERSION}"
VIAddVersionKey "CompanyName" "Dr. Szaba"
VIAddVersionKey "FileDescription" "${APPNAME} Setup"
VIAddVersionKey "LegalCopyright" "Dr. Szaba"

!define MUI_ICON "app\assets\icon.ico"
!define MUI_UNICON "app\assets\icon.ico"
!define MUI_WELCOMEFINISHPAGE_BITMAP "wizard.bmp"
!define MUI_WELCOMEPAGE_TITLE "Welcome to ${APPNAME} ${VERSION}"
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_FUNCTION StartApp
!define MUI_FINISHPAGE_RUN_TEXT "Start ${APPNAME} now"
!define MUI_ABORTWARNING

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Function StartApp
  Exec '"$INSTDIR\python\pythonw.exe" "$INSTDIR\app\run_app.py"'
FunctionEnd

Section "Install"
  ; the updater starts us right after the app closes - give it a moment
  Sleep 1500
  SetOverwrite on
  SetOutPath "$INSTDIR"
  File "README.txt"
  File "LICENSES.txt"
  File /r "app"
  File /r "python"
  File /r "ffmpeg"

  WriteUninstaller "$INSTDIR\Uninstall.exe"

  CreateDirectory "$SMPROGRAMS\${APPNAME}"
  CreateShortcut "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk" "$INSTDIR\python\pythonw.exe" '"$INSTDIR\app\run_app.py"' "$INSTDIR\app\assets\icon.ico"
  CreateShortcut "$SMPROGRAMS\${APPNAME}\Uninstall ${APPNAME}.lnk" "$INSTDIR\Uninstall.exe"
  CreateShortcut "$DESKTOP\${APPNAME}.lnk" "$INSTDIR\python\pythonw.exe" '"$INSTDIR\app\run_app.py"' "$INSTDIR\app\assets\icon.ico"

  WriteRegStr HKCU "${REGKEY}" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "${REGKEY}" "Version" "${VERSION}"

  WriteRegStr HKCU "Software\Classes\.ezvm" "" "EZVideoMaker.Project"
  WriteRegStr HKCU "Software\Classes\EZVideoMaker.Project" "" "EZ Video Maker project"
  WriteRegStr HKCU "Software\Classes\EZVideoMaker.Project\DefaultIcon" "" "$INSTDIR\app\assets\icon.ico"
  WriteRegStr HKCU "Software\Classes\EZVideoMaker.Project\shell\open\command" "" '"$INSTDIR\python\pythonw.exe" "$INSTDIR\app\run_app.py" "%1"'

  WriteRegStr HKCU "${UNKEY}" "DisplayName" "${APPNAME}"
  WriteRegStr HKCU "${UNKEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNKEY}" "Publisher" "Dr. Szaba"
  WriteRegStr HKCU "${UNKEY}" "DisplayIcon" "$INSTDIR\app\assets\icon.ico"
  WriteRegStr HKCU "${UNKEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNKEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "${UNKEY}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
  WriteRegDWORD HKCU "${UNKEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNKEY}" "NoRepair" 1
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKCU "${UNKEY}" "EstimatedSize" "$0"

  ; started by the updater with "Restart & update now": open the app again
  ${GetParameters} $R0
  ClearErrors
  ${GetOptions} $R0 "/UPDATE" $R1
  ${IfNot} ${Errors}
    Exec '"$INSTDIR\python\pythonw.exe" "$INSTDIR\app\run_app.py"'
  ${EndIf}
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\${APPNAME}.lnk"
  RMDir /r "$SMPROGRAMS\${APPNAME}"
  RMDir /r "$INSTDIR\app"
  RMDir /r "$INSTDIR\python"
  RMDir /r "$INSTDIR\ffmpeg"
  Delete "$INSTDIR\README.txt"
  Delete "$INSTDIR\LICENSES.txt"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "${UNKEY}"
  DeleteRegKey HKCU "${REGKEY}"
  DeleteRegKey HKCU "Software\Classes\.ezvm"
  DeleteRegKey HKCU "Software\Classes\EZVideoMaker.Project"
SectionEnd
