!include "x64.nsh"
!macro customInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "WinWhisper Studio benötigt Windows x64."
    Quit
  ${EndIf}
!macroend

!macro customUnInstall
  ; User recordings, models and projects deliberately remain in userData.
!macroend
