' Lance la fenetre du bench lock sans faire clignoter de console, meme au demarrage
' (double-clic sur ce fichier ; bench-gui.cmd fait pareil mais montre un cmd une seconde).
Set shell = CreateObject("WScript.Shell")
here = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
shell.Run "pythonw -I """ & here & "bench_gui.pyw""", 0, False
